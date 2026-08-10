#include <stdexcept>
#include <string>
#include <vector>

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <vpi/Array.h>
#include <vpi/Image.h>
#include <vpi/ImageFormat.h>
#include <vpi/PixelType.h>
#include <vpi/Stream.h>
#include <vpi/algo/AprilTags.h>

namespace py = pybind11;

static void check(VPIStatus status, const char *operation)
{
    if (status == VPI_SUCCESS) return;
    char detail[VPI_MAX_STATUS_MESSAGE_LENGTH] = {};
    vpiGetLastStatusMessage(detail, sizeof(detail));
    throw std::runtime_error(std::string(operation) + ": " + vpiStatusGetName(status) + " (" + detail + ")");
}

static VPIImageData wrapGray(void *pointer, int width, int height, int pitch)
{
    VPIImageData data{};
    data.bufferType = VPI_IMAGE_BUFFER_HOST_PITCH_LINEAR;
    data.buffer.pitch.format = VPI_IMAGE_FORMAT_U8;
    data.buffer.pitch.numPlanes = 1;
    data.buffer.pitch.planes[0].pixelType = VPI_PIXEL_TYPE_U8;
    data.buffer.pitch.planes[0].width = width;
    data.buffer.pitch.planes[0].height = height;
    data.buffer.pitch.planes[0].pitchBytes = pitch;
    data.buffer.pitch.planes[0].data = pointer;
    return data;
}

class Detector
{
public:
    Detector(int width, int height, bool usePVA, int maxDetections = 16)
        : width_(width), height_(height), maxDetections_(maxDetections),
          backend_(usePVA ? VPI_BACKEND_PVA : VPI_BACKEND_CPU),
          flags_(usePVA ? (VPI_BACKEND_PVA | VPI_BACKEND_CPU) : VPI_BACKEND_CPU),
          placeholder_(static_cast<size_t>(width) * height, 0)
    {
        try {
            VPIAprilTagDecodeParams params;
            check(vpiInitAprilTagDecodeParams(&params), "vpiInitAprilTagDecodeParams");
            params.family = VPI_APRILTAG_36H11;
            params.maxBitsCorrected = 1;
            check(vpiStreamCreate(flags_, &stream_), "vpiStreamCreate");
            check(vpiCreateAprilTagDetector(backend_, width, height, &params, &payload_),
                  "vpiCreateAprilTagDetector");
            VPIImageData imageData = wrapGray(placeholder_.data(), width, height, width);
            check(vpiImageCreateWrapper(&imageData, nullptr, flags_, &input_),
                  "vpiImageCreateWrapper");
            check(vpiArrayCreate(maxDetections_, VPI_ARRAY_TYPE_APRILTAG_DETECTION, flags_, &detections_),
                  "vpiArrayCreate");
        } catch (...) {
            cleanup();
            throw;
        }
    }

    ~Detector() { cleanup(); }

    py::list detect(py::array_t<uint8_t, py::array::c_style | py::array::forcecast> image)
    {
        auto info = image.request();
        if (info.ndim != 2 || info.shape[0] != height_ || info.shape[1] != width_)
            throw std::invalid_argument("expected uint8 grayscale image with configured height and width");

        VPIImageData imageData = wrapGray(info.ptr, width_, height_, static_cast<int>(info.strides[0]));
        check(vpiImageSetWrapper(input_, &imageData), "vpiImageSetWrapper");
        {
            py::gil_scoped_release release;
            check(vpiSubmitAprilTagDetector(stream_, backend_, payload_, maxDetections_, input_, detections_),
                  "vpiSubmitAprilTagDetector");
            check(vpiStreamSync(stream_), "vpiStreamSync");
        }

        VPIArrayData data{};
        check(vpiArrayLockData(detections_, VPI_LOCK_READ, VPI_ARRAY_BUFFER_HOST_AOS, &data),
              "vpiArrayLockData");
        py::list output;
        try {
            const int size = *data.buffer.aos.sizePointer;
            auto *items = static_cast<VPIAprilTagDetection *>(data.buffer.aos.data);
            for (int i = 0; i < size; ++i) {
                py::array_t<float> corners({4, 2});
                auto c = corners.mutable_unchecked<2>();
                for (int j = 0; j < 4; ++j) {
                    c(j, 0) = items[i].corners[j].x;
                    c(j, 1) = items[i].corners[j].y;
                }
                output.append(py::make_tuple(items[i].id, corners, items[i].decisionMargin,
                                             items[i].correctedBits));
            }
        } catch (...) {
            vpiArrayUnlock(detections_);
            throw;
        }
        check(vpiArrayUnlock(detections_), "vpiArrayUnlock");
        return output;
    }

    std::string backend() const { return backend_ == VPI_BACKEND_PVA ? "PVA" : "CPU"; }

private:
    void cleanup()
    {
        if (stream_) vpiStreamSync(stream_);
        if (detections_) vpiArrayDestroy(detections_);
        if (input_) vpiImageDestroy(input_);
        if (payload_) vpiPayloadDestroy(payload_);
        if (stream_) vpiStreamDestroy(stream_);
        detections_ = nullptr; input_ = nullptr; payload_ = nullptr; stream_ = nullptr;
    }

    int width_, height_, maxDetections_;
    uint64_t backend_, flags_;
    std::vector<uint8_t> placeholder_;
    VPIStream stream_ = nullptr;
    VPIPayload payload_ = nullptr;
    VPIImage input_ = nullptr;
    VPIArray detections_ = nullptr;
};

PYBIND11_MODULE(vpi_apriltag, module)
{
    module.doc() = "NVIDIA VPI AprilTag 36h11 detector binding";
    py::class_<Detector>(module, "Detector")
        .def(py::init<int, int, bool, int>(), py::arg("width"), py::arg("height"),
             py::arg("use_pva") = true, py::arg("max_detections") = 16)
        .def("detect", &Detector::detect)
        .def_property_readonly("backend", &Detector::backend);
}
