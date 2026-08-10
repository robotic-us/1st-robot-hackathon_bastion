#include <cstdio>
#include <cstring>
#include <array>

#include <soem/ethercat.h>

int main(int argc, char **argv)
{
  const char *nic = argc > 1 ? argv[1] : "eno1";
  if (!ec_init(nic)) {
    std::fprintf(stderr, "ec_init(%s) failed\n", nic);
    return 1;
  }
  if (ec_config_init(FALSE) <= 0) {
    std::fprintf(stderr, "no EtherCAT slave found\n");
    ec_close();
    return 2;
  }
  std::printf("slaves=%d\n", ec_slavecount);
  for (int slave = 1; slave <= ec_slavecount; ++slave) {
    std::printf("slave=%d name=%s state=0x%02x\n", slave, ec_slave[slave].name,
                ec_slave[slave].state);
    ec_ODlistt od{};
    od.Slave = static_cast<uint16>(slave);
    const int wkc = ec_readODlist(static_cast<uint16>(slave), &od);
    std::printf("OD entries=%u wkc=%d\n", od.Entries, wkc);
    for (uint16 item = 0; item < od.Entries; ++item) {
      if (ec_readODdescription(item, &od) <= 0) {
        std::printf("0x%04X <description unavailable>\n", od.Index[item]);
        continue;
      }
      ec_OElistt oe{};
      const int oewkc = ec_readOE(item, &od, &oe);
      std::printf("0x%04X code=0x%02X dtype=0x%04X maxsub=%u name=%s oe_wkc=%d\n",
                  od.Index[item], od.ObjectCode[item], od.DataType[item], od.MaxSub[item],
                  od.Name[item], oewkc);
      if (oewkc > 0) {
        for (uint16 sub = 0; sub <= od.MaxSub[item] && sub < EC_MAXOELIST; ++sub) {
          if (oe.BitLength[sub] == 0 && oe.Name[sub][0] == '\0') { continue; }
          std::printf("  :%02X dtype=0x%04X bits=%u access=0x%04X name=%s\n", sub,
                      oe.DataType[sub], oe.BitLength[sub], oe.ObjAccess[sub], oe.Name[sub]);
        }
      }
    }

    if (od.Entries == 0) {
      std::puts("OD-list unsupported; probing readable manufacturer objects (read-only)");
      const std::array<std::pair<uint16, uint16>, 8> ranges{{
        {0x2000u, 0x21FFu}, {0x3000u, 0x30FFu}, {0x4000u, 0x43FFu},
        {0x5000u, 0x50FFu}, {0x5F00u, 0x5F0Du}, {0x6000u, 0x60FFu}, {0x7000u, 0x70FFu},
        {0x8000u, 0x80FFu}
      }};
      for (const auto &range : ranges) {
        for (uint32 index = range.first; index <= range.second; ++index) {
          for (uint8 sub = 0; sub <= 1; ++sub) {
            uint8 data[256]{};
            int size = static_cast<int>(sizeof(data));
            const int rwkc = ec_SDOread(static_cast<uint16>(slave), static_cast<uint16>(index),
                                       sub, FALSE, &size, data, 20000);
            if (rwkc <= 0) { continue; }
            std::printf("READ 0x%04X:%02X len=%d data=", static_cast<unsigned>(index), sub, size);
            for (int i = 0; i < size; ++i) { std::printf("%02X", data[i]); }
            std::putchar('\n');
            if (sub == 0 && size == 1 && data[0] > 1 && data[0] <= 64) {
              for (uint8 extra = 2; extra <= data[0]; ++extra) {
                uint8 extra_data[256]{};
                int extra_size = static_cast<int>(sizeof(extra_data));
                const int extra_wkc = ec_SDOread(
                  static_cast<uint16>(slave), static_cast<uint16>(index), extra, FALSE,
                  &extra_size, extra_data, 20000);
                if (extra_wkc <= 0) { continue; }
                std::printf("READ 0x%04X:%02X len=%d data=", static_cast<unsigned>(index),
                            extra, extra_size);
                for (int i = 0; i < extra_size; ++i) { std::printf("%02X", extra_data[i]); }
                std::putchar('\n');
              }
            }
          }
        }
      }
    }
  }
  ec_close();
  return 0;
}
