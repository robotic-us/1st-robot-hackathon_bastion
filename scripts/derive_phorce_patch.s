.text
.global patch_insns
patch_insns:
    cmp x0, #0x1c7
    mov w4, #0x1c7
    cmp w0, #3
