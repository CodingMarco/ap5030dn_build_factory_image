import zlib
import argparse
from dataclasses import dataclass


# Metadata header:
# - CRC32 Checksum of all data before this checksum except 32-byte header (eg. `BB CC B5 37` for FatAP5X30XN_V200R010C00SPCf01.bin)
# - sizeof(primary kernel)
# - sizeof(squashfs) == Beginn addr of first uImage header (excluding 32-byte header)
# - sizeof(u-boot)
# - 3x `00 00 00 00`
# - `07 00 00 00`
# - sizeof(backup kernel) + 40
# - `02 00 00 00`
# - `70 05 00 00` = 1392(dec)


@dataclass
class Metadata:
    crc32_checksum: int
    primary_kernel_size: int
    squashfs_size: int
    uboot_size: int
    backup_kernel_size: int

    def pack_metadata(self):
        return (
            self.crc32_checksum.to_bytes(4, byteorder="little")
            + self.primary_kernel_size.to_bytes(4, byteorder="little")
            + self.squashfs_size.to_bytes(4, byteorder="little")
            + self.uboot_size.to_bytes(4, byteorder="little")
            + 3 * b"\x00\x00\x00\x00"
            + b"\x07\x00\x00\x00"
            + (self.backup_kernel_size + 40).to_bytes(4, byteorder="little")
            + int(2).to_bytes(4, byteorder="little")
            + b"\x70\x05\x00\x00"
        )


def load_binary(path):
    with open(path, "rb") as f:
        return f.read()


header_data = load_binary("static/header.bin")
uboot_data = load_binary("static/uboot.bin")
metadata_header_data = load_binary("static/metadata_header.bin")
metadata_footer_data = load_binary("static/metadata_footer.bin")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", help="Output file")
    parser.add_argument("-k", "--kernel", help="Kernel image", required=True)
    parser.add_argument("-r", "--rootfs", help="Rootfs image", required=True)
    parser.add_argument(
        "--ramdisk",
        help="Kernel + ramdisk image used as 2nd kernel/system",
        required=False,
    )

    return parser.parse_args()


def load_user_data(args):
    kernel_data = load_binary(args.kernel)
    rootfs_data = load_binary(args.rootfs)
    # Just use the same kernel image two times if no ramdisk is specified
    ramdisk_data = load_binary(args.ramdisk) if args.ramdisk else kernel_data

    return kernel_data, rootfs_data, ramdisk_data


def append_data(original, data, alignment):
    # Align the data
    data += b"\x00" * (alignment - ((len(original) + len(data)) % alignment))

    return original + data, len(data)


def main():
    alignment = 16  # 16 bytes
    args = parse_args()
    kernel_data, rootfs_data, ramdisk_data = load_user_data(args)

    final_data = header_data
    final_data, rootfs_len = append_data(final_data, rootfs_data, alignment)
    final_data, kernel_len = append_data(final_data, kernel_data, alignment)
    final_data, uboot_len = append_data(final_data, uboot_data, alignment)
    final_data, ramdisk_len = append_data(final_data, ramdisk_data, alignment)
    final_data += metadata_header_data

    print(f"Rootfs size: {rootfs_len} / 0x{rootfs_len:x}")
    print(f"Kernel size: {kernel_len} / 0x{kernel_len:x}")
    print(f"Uboot size: {uboot_len} / 0x{uboot_len:x}")
    print(f"Ramdisk size: {ramdisk_len} / 0x{ramdisk_len:x}")

    crc32_checksum = zlib.crc32(final_data[32:])

    metadata = Metadata(
        crc32_checksum=crc32_checksum,
        primary_kernel_size=kernel_len,
        squashfs_size=rootfs_len,
        uboot_size=uboot_len,
        backup_kernel_size=ramdisk_len,
    )

    final_data += metadata.pack_metadata()
    final_data += metadata_footer_data

    with open(args.output, "wb") as f:
        f.write(final_data)


if __name__ == "__main__":
    main()
