#!/usr/bin/python2

"""Pack and unpack Xamarin AssemblyStore files"""

from __future__ import print_function
import struct
import argparse
import os
import os.path
import sys
import json

import lz4.block
import xxhash

from . import constants


class ManifestEntry(object):

    """Element in Manifest"""

    hash32 = ""
    hash64 = ""
    blob_id = 0
    blob_idx = 0
    name = ""

    def __init__(self, hash32, hash64, blob_id, blob_idx, name):

        """Initialize item"""

        self.hash32 = hash32
        self.hash64 = hash64
        self.blob_id = int(blob_id)
        self.blob_idx = int(blob_idx)
        self.name = name


class ManifestList(list):

    """List of manifest entries"""

    def get_idx(self, blob_id, blob_idx):

        """Find entry by ID"""

        for entry in self:
            if entry.blob_idx == blob_idx and entry.blob_id == blob_id:
                return entry
        return None


class AssemblyStoreAssembly(object):

    """Assembly Details"""

    data_offset = 0
    data_size = 0
    debug_data_offset = 0
    debug_data_size = 0
    config_data_offset = 0
    config_data_size = 0

    def __init__(self):
        pass


class AssemblyStoreHashEntry(object):

    """Hash Details"""

    hash_val = ""
    mapping_index = 0
    local_store_index = 0
    store_id = 0

    def __init__(self):
        pass


class AssemblyStore(object):

    """AssemblyStore object"""

    raw = ""

    file_name = ""

    manifest_entries = None

    hdr_magic = ""
    hdr_version = 0
    hdr_lec = 0
    hdr_gec = 0
    hdr_store_id = 0

    assembly_list = None
    global_hash32 = None
    global_hash64 = None

    def __init__(self, in_file_name, manifest_entries):

        """Parse and read store"""

        self.manifest_entries = manifest_entries
        self.file_name = os.path.basename(in_file_name)

        blob_file = open(in_file_name, "rb")

        self.raw = blob_file.read()

        blob_file.seek(0)

        # Header Section
        #
        # 0  -  3: Magic
        # 4  -  7: Version
        # 8  - 11: LocalEntryCount
        # 12 - 15: GlobalEntryCount
        # 16 - 19: StoreID

        magic = blob_file.read(4)
        if magic != constants.ASSEMBLY_STORE_MAGIC:
            raise Exception("Invalid Magic: %s" % magic)

        version = struct.unpack("I", blob_file.read(4))[0]
        if version > constants.ASSEMBLY_STORE_FORMAT_VERSION:
            raise Exception("This version is higher than expected! Max = %d, got %d"
                            % constants.ASSEMBLY_STORE_FORMAT_VERSION, version)

        self.hdr_version = version

        self.hdr_lec = struct.unpack("I", blob_file.read(4))[0]
        self.hdr_gec = struct.unpack("I", blob_file.read(4))[0]
        self.hdr_store_id = struct.unpack("I", blob_file.read(4))[0]

        print("Local entry count: %d" % self.hdr_lec)
        print("Global entry count: %d" % self.hdr_gec)

        self.assemblies_list = list()

        # print("Entries start at: %d (0x%x)" % (blob_file.tell(), blob_file.tell()))

        i = 0
        while i < self.hdr_lec:

            #  0 -  3: DataOffset
            #  4 -  7: DataSize
            #  8 - 11: DebugDataOffset
            # 12 - 15: DebugDataSize
            # 16 - 19: ConfigDataOffset
            # 20 - 23: ConfigDataSize

            # print("Extracting Assembly: %d (0x%x)" % (blob_file.tell(), blob_file.tell()))
            entry = blob_file.read(24)

            assembly = AssemblyStoreAssembly()

            assembly.data_offset = struct.unpack("I", entry[0:4])[0]
            assembly.data_size = struct.unpack("I", entry[4:8])[0]
            assembly.debug_data_offset = struct.unpack("I", entry[8:12])[0]
            assembly.debug_data_size = struct.unpack("I", entry[12:16])[0]
            assembly.config_data_offset = struct.unpack("I", entry[16:20])[0]
            assembly.config_data_size = struct.unpack("I", entry[20:24])[0]

            self.assemblies_list.append(assembly)

            print("  Data Offset: %d (0x%x)" % (assembly.data_offset, assembly.data_offset))
            print("  Data Size: %d (0x%x)" % (assembly.data_size, assembly.data_size))
            print("  Config Offset: %d (0x%x)" % (assembly.config_data_offset, assembly.config_data_offset))
            print("  Config Size: %d (0x%x)" % (assembly.config_data_size, assembly.config_data_size))
            print("  Debug Offset: %d (0x%x)" % (assembly.debug_data_offset, assembly.debug_data_offset))
            print("  Debug Size: %d (0x%x)" % (assembly.debug_data_size, assembly.debug_data_size))

            i += 1

        # Parse Hash data
        #
        # The following 2 sections are _required_ to be in order from
        # lowest to highest (e.g. 0x00000000 to 0xffffffff).
        # Since you're very likely not going to be adding assemblies
        # (or renaming) to the store, I'm going to store the hashes with the
        # assemblies.json to make sorting easier when packing.

        # print("Hash32 start at: %d (0x%x)" % (blob_file.tell(), blob_file.tell()))
        self.global_hash32 = list()

        i = 0
        while i < self.hdr_lec:

            entry = blob_file.read(20)

            hash_entry = AssemblyStoreHashEntry()

            hash_entry.hash_val = "0x%08x" % struct.unpack("<I", entry[0:4])[0]
            hash_entry.mapping_index = struct.unpack("I", entry[8:12])[0]
            hash_entry.local_store_index = struct.unpack("I", entry[12:16])[0]
            hash_entry.store_id = struct.unpack("I", entry[16:20])[0]

            print("   mapping index: %d" % hash_entry.mapping_index)
            print("   local store index: %d" % hash_entry.local_store_index)
            print("   store id: %d" % hash_entry.store_id)

            self.global_hash32.append(hash_entry)

            i += 1

        # print("Hash64 start at: %d (0x%x)" % (blob_file.tell(), blob_file.tell()))
        self.global_hash64 = list()

        i = 0
        while i < self.hdr_lec:

            entry = blob_file.read(20)

            hash_entry = AssemblyStoreHashEntry()

            hash_entry.hash_val = "0x%016x" % struct.unpack("<Q", entry[0:8])[0]
            hash_entry.mapping_index = struct.unpack("I", entry[8:12])[0]
            hash_entry.local_store_index = struct.unpack("I", entry[12:16])[0]
            hash_entry.store_id = struct.unpack("I", entry[16:20])[0]

            self.global_hash64.append(hash_entry)

            i += 1

    def extract_all(self, json_config, outpath="out"):

        """Extract everything"""

        # Start the config JSON
        store_json = dict()

        # Set the JSON header data
        store_json['header'] = {'version': self.hdr_version,
                                'lec': self.hdr_lec,
                                'gec': self.hdr_gec,
                                'store_id': self.hdr_store_id}


        # Set JSON assembly data and start parsing.
        store_json['assemblies'] = list()

        i = 0
        for assembly in self.assemblies_list:

            # Set assembly JSON dictionary
            assembly_dict = dict()

            # Assume no compression
            assembly_dict['lz4'] = False

            assembly_data = ""

            entry = self.manifest_entries.get_idx(self.hdr_store_id, i)

            # Save hash/name/idx to JSON
            assembly_dict['name'] = entry.name
            assembly_dict['id'] = entry.blob_id
            assembly_dict['idx'] = entry.blob_idx
            assembly_dict['hash32'] = entry.hash32
            assembly_dict['hash64'] = entry.hash64

            # Set and save outpath
            out_file = "%s/%s.dll" % (outpath, entry.name)
            assembly_dict['file'] = out_file

            # Check if compressed, otherwise write
            assembly_header = self.raw[assembly.data_offset:assembly.data_offset+4]
            if assembly_header == constants.COMPRESSED_DATA_MAGIC:

                assembly_data = self.decompress_lz4(self.raw[assembly.data_offset:
                                                    assembly.data_offset
                                                    + assembly.data_size])
                assembly_dict['lz4'] = True
                assembly_dict['lz4_desc_idx'] = struct.unpack('<I',
                                                    self.raw[assembly.data_offset + 4:
                                                    assembly.data_offset + 8])[0]
            else:
                assembly_data = self.raw[assembly.data_offset:
                                         assembly.data_offset + assembly.data_size]

            print("Extracting %s..." % entry.name)
            if not os.path.isdir(os.path.dirname(out_file)):
                os.mkdir(os.path.dirname(out_file))
            wfile = open(out_file, "wb")

            wfile.write(assembly_data)
            wfile.close()

            # Append to assemblies JSON
            store_json['assemblies'].append(assembly_dict)

            i += 1

        json_config['stores'][self.file_name] = store_json
        return json_config

    @classmethod
    def decompress_lz4(cls, compressed_data):

        """Unpack an assembly if LZ4 packed"""

        # From: https://github.com/securitygrind/lz4_decompress

        packed_payload_len = compressed_data[8:12]
        unpacked_payload_len = struct.unpack('<I', packed_payload_len)[0]
        compressed_payload = compressed_data[12:]

        return lz4.block.decompress(compressed_payload,
                                    uncompressed_size=unpacked_payload_len)


def lz4_compress(file_data, desc_idx):

    """LZ4 compress data stream + add header"""

    # 00 - 03: header XALZ
    # 04 - 07: desc_index (not the same as idx?)
    # 08 - 11: packed_payload_len
    # 12 -  n: compressed data

    packed = struct.pack("4sII",
                         constants.COMPRESSED_DATA_MAGIC,
                         desc_idx,
                         len(file_data))

    # https://github.com/xamarin/xamarin-android/blob/681887ebdbd192ce7ce1cd02221d4939599ba762/src/Xamarin.Android.Build.Tasks/Utilities/AssemblyCompression.cs#L81
    compressed_data = lz4.block.compress(file_data, mode='high_compression',
                                         store_size=False, compression=9)

    packed += compressed_data

    return packed


def gen_xxhash(name, raw=False):

    """Generate xxhash32 + 64"""

    h32 = xxhash.xxh32(seed=0)
    h64 = xxhash.xxh64(seed=0)

    h32.update(name)
    h64.update(name)

    if raw:
        return h32.digest()[::-1], h64.digest()[::-1]

    return h32.hexdigest(), h64.hexdigest()


def read_manifest(in_manifest):

    """Read Manifest entries"""

    manifest_list = ManifestList()
    for line in open(in_manifest, "rb").read().split(b"\n"):
        if line == "" or len(line) == 0:
            continue
        if line[0:4] == "Hash":
            continue

        split_line = line.split()

        manifest_list.append(ManifestEntry(split_line[0].decode(),   # hash32
                                           split_line[1].decode(),   # hash64
                                           split_line[2],            # blob_id
                                           split_line[3],            # blob_idx
                                           split_line[4].decode()))  # name

    return manifest_list


def usage():

    """Print usage"""

    print("usage: xamstore MODE <args>")
    print("")
    print("   MODES:")
    print("\tunpack <args>  Unpack assembly blobs.")
    print("\tpack <args>    Repackage assembly blobs.")
    print("\thash file_name Generate xxHash values.")
    print("\thelp           Print this message.")

    return 0


def do_unpack(in_directory, in_arch):

    """Unpack a assemblies.blob/manifest"""

    arch_assemblies = False

    # First check if all files exist.
    if os.path.isdir("out/"):
        print("Out directory already exists!")
        return 3

    manifest_path = os.path.join(in_directory, constants.FILE_ASSEMBLIES_MANIFEST)
    assemblies_path = os.path.join(in_directory, constants.FILE_ASSEMBLIES_BLOB)

    if not os.path.isfile(manifest_path):
        print("Manifest file '%s' does not exist!" % manifest_path)
        return 4
    elif not os.path.isfile(assemblies_path):
        print("Main assemblies blob '%s' does not exist!" % assemblies_path)
        return 4

    # The manifest will have all entries (regardless of which
    # *.blob they're found in. Parse this first, and then handle
    # each blob.

    manifest_entries = read_manifest(manifest_path)
    if manifest_entries is None:
        print("Unable to parse assemblies.manifest file!")
        return 5

    # Next we'll unpack each *.blob file. The JSON output will be broken
    # broken up my file name. Generally, the stucture will be:
    #
    # assemblies.blob {
    #   header { .. },
    #   assemblies { [ .. ] }
    # },
    # assemblies.arm.blob {
    #   ..
    # }
    json_data = dict()
    json_data['stores'] = dict()

    os.mkdir("out/")

    assembly_store = AssemblyStore(assemblies_path, manifest_entries)

    if assembly_store.hdr_lec != assembly_store.hdr_gec:
        arch_assemblies = True
        print("There are more assemblies to unpack here!")

    # Do extraction.
    json_data = assembly_store.extract_all(json_data)

    # What about architecture assemblies?
    if arch_assemblies:
        arch_assemblies_path = os.path.join(in_directory,
                                            constants.ARCHITECTURE_MAP[in_arch])

        arch_assembly_store = AssemblyStore(arch_assemblies_path,
                                            manifest_entries)
        json_data = arch_assembly_store.extract_all(json_data)

    # Save the large config out.
    with open(constants.FILE_ASSEMBLIES_JSON, 'w') as assembly_file:
        assembly_file.write(json.dumps(json_data, indent=4))

def do_pack(in_json_config):

    """Create new assemblies.blob/manifest"""

    if not os.path.isfile(in_json_config):
        print("Config file '%s' does not exist!" % in_json_config)
        return -1

    if os.path.isfile("assemblies.manifest.new"):
        print("Output manifest exists!")
        return -2

    if os.path.isfile("assemblies.blob.new"):
        print("Output blob exists!")
        return -3

    json_data = None
    with open(in_json_config, "r") as json_f:
        json_data = json.load(json_f)

    # Write new assemblies.manifest
    print("Writing 'assemblies.manifest.new'...")
    assemblies_manifest_f = open("assemblies.manifest.new", "w")

    assemblies_manifest_f.write("Hash 32     Hash 64             ")
    assemblies_manifest_f.write("Blob ID  Blob idx  Name\r\n")

    for assembly in json_data['assemblies']:
        hash32, hash64 = gen_xxhash(assembly['name'])
        line = ("0x%08s  0x%016s  000      %04d      %s\r\n"
                % (hash32, hash64, assembly['idx'], assembly['name']))

        assemblies_manifest_f.write(line)

    assemblies_manifest_f.close()

    # Pack the new AssemblyStore structure
    print("Writing 'assemblies.blob.new'...")
    assemblies_blob_f = open("assemblies.blob.new", "wb")

    # Write header
    json_hdr = json_data['header']
    assemblies_blob_f.write(struct.pack("4sIIII",
                                        constants.ASSEMBLY_STORE_MAGIC,
                                        json_hdr['version'],
                                        json_hdr['lec'],
                                        json_hdr['gec'],
                                        json_hdr['store_id']))

    next_entry_offset = 20
    next_data_offset = 20 + (json_hdr['lec'] * 24) + (json_hdr['lec'] * 40)

    # First pass: Write the entries + DLL content.
    for assembly in json_data['assemblies']:

        assembly_data = open(assembly['file'], "rb").read()
        if assembly['lz4']:
            assembly_data = lz4_compress(assembly_data,
                                         assembly['lz4_desc_idx'])

        data_size = len(assembly_data)

        # Write the entry data
        assemblies_blob_f.seek(next_entry_offset)
        assemblies_blob_f.write(struct.pack("IIIIII",
                                            next_data_offset,
                                            data_size,
                                            0, 0, 0, 0))

        # Write binary data
        assemblies_blob_f.seek(next_data_offset)
        assemblies_blob_f.write(assembly_data)

        # Move all offsets forward.
        next_data_offset += data_size
        next_entry_offset += 24

    # Second + third pass: sort the hashes and write them
    next_hash32_offset = 20 + (json_hdr['lec'] * 24)
    next_hash64_offset = 20 + (json_hdr['lec'] * 24) + (json_hdr['lec'] * 20)

    assembly_data = json_data["assemblies"]

    # hash32
    for assembly in sorted(assembly_data, key=lambda d: d['hash32']):

        # Hash sections
        hash32, hash64 = gen_xxhash(assembly['name'], raw=True)

        # Write the hash32
        assemblies_blob_f.seek(next_hash32_offset)
        assemblies_blob_f.write(struct.pack("4sIIII",
                                            hash32,
                                            0,
                                            assembly['idx'],
                                            assembly['idx'],
                                            0))

        next_hash32_offset += 20

    # hash64
    for assembly in sorted(assembly_data, key=lambda d: d['hash64']):

        # Hash sections
        hash32, hash64 = gen_xxhash(assembly['name'], raw=True)

        # Write the hash64
        assemblies_blob_f.seek(next_hash64_offset)
        assemblies_blob_f.write(struct.pack("8sIII",
                                            hash64,
                                            assembly['idx'],
                                            assembly['idx'],
                                            0))

        next_hash64_offset += 20

    # Done!
    assemblies_blob_f.close()

    return 0


def unpack_store(args):

    """Unpack an assemblies store"""

    parser = argparse.ArgumentParser(prog='xamstore unpack',
                                     description='Unpack DLLs from assemblies.blob store.')
    parser.add_argument('--dir', '-d', type=str, metavar='val',
                        default='./',
                        dest='directory',
                        help='Where to load blobs/manifest from.')
    parser.add_argument('--arch', '-a', type=str, metavar='val',
                        default='arm64',
                        dest='architecture',
                        help='Which architecture to unpack: arm(64), x86(_64)')

    parsed_args = parser.parse_args(args)

    return do_unpack(parsed_args.directory,
                     parsed_args.architecture)


def pack_store(args):

    """Pack an assemblies store"""

    parser = argparse.ArgumentParser(prog='xamstore pack',
                                     description='Repackage DLLs into assemblies.blob.')
    parser.add_argument('--config', '-c', type=str, metavar='val',
                        default='assemblies.json',
                        dest='config_json',
                        help='Input assemblies.blob file.')

    parsed_args = parser.parse_args(args)

    if not os.path.isfile(parsed_args.config_json):
        print("File '%s' doesn't exist!" % parsed_args.config_json)
        return -3

    return do_pack(parsed_args.config_json)


def hash_file(args):

    """Generate xxhashes for a given file, mostly for testing"""

    if len(args) < 1:
        print("Need to provide a file to hash!")
        return -1

    file_name = args.pop(0)
    hash_name = os.path.splitext(os.path.basename(file_name))[0]

    print("Generating hashes for file '%s (%s)" % (file_name, hash_name))
    hash32, hash64 = gen_xxhash(hash_name)

    print("Hash32: 0x%s" % hash32)
    print("Hash64: 0x%s" % hash64)

    return 0


def main():

    """Main Loop"""

    if len(sys.argv) < 2:
        print("Mode is required!")
        return -1

    sys.argv.pop(0)
    mode = sys.argv.pop(0)

    if mode == "unpack":
        return unpack_store(sys.argv)
    elif mode == "pack":
        return pack_store(sys.argv)
    elif mode == "hash":
        return hash_file(sys.argv)
    elif mode in ['-h', '--h', 'help']:
        return usage()

    print("Unknown mode: '%s'" % mode)
    return -2


if __name__ == "__main__":
    main()