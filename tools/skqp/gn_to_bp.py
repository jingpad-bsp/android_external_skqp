#!/usr/bin/env python
#
# Copyright 2016 Google Inc.
#
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Generate Android.bp for Skia from GN configuration.

import argparse
import json
import os
import pprint
import string
import subprocess
import sys
import tempfile

root_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        os.pardir, os.pardir)
skia_gn_dir = os.path.join(root_dir, 'gn')
sys.path.insert(0, skia_gn_dir)

import gn_to_bp_utils

from skqp_gn_args import SkqpGnArgs

# First we start off with a template for Android.bp,
# with holes for source lists and include directories.
bp = string.Template('''// This file is autogenerated by tools/skqp/gn_to_bp.py.

cc_library_shared {
    name: "libskqp_app",
    sdk_version: "26",
    stl: "libc++_static",
    compile_multilib: "both",

    cflags: [
        $cflags
        "-Wno-unused-parameter",
        "-Wno-unused-variable",
    ],

    cppflags:[
        $cflags_cc
    ],

    local_include_dirs: [
        $local_includes
    ],

    srcs: [
        "third_party/vulkanmemoryallocator/GrVulkanMemoryAllocator.cpp",
        $srcs
    ],

    arch: {
        arm: {
            srcs: [
                $arm_srcs
            ],

            neon: {
                srcs: [
                    $arm_neon_srcs
                ],
            },
        },

        arm64: {
            srcs: [
                $arm64_srcs
            ],
        },

        mips: {
            srcs: [
                $none_srcs
            ],
        },

        mips64: {
            srcs: [
                $none_srcs
            ],
        },

        x86: {
            srcs: [
                $x86_srcs
            ],
        },

        x86_64: {
            srcs: [
                $x86_srcs
            ],
        },
    },

    shared_libs: [
          "libandroid",
          "libEGL",
          "libGLESv2",
          "liblog",
          "libvulkan",
          "libz",
    ],
    static_libs: [
          "libexpat",
          "libjpeg_static_ndk",
          "libjsoncpp_ndk",
          "libpng_ndk",
          "libwebp-decode",
          "libwebp-encode",
    ]
}''')

# We'll run GN to get the main source lists and include directories for Skia.
gn_args = {
  'target_cpu': '"none"',
  'target_os':  '"android"',

  # setup skqp
  'is_debug':   'false',
  'ndk_api':    '26',

  # specify that the Android.bp will supply the necessary components
  'skia_use_system_expat':         'true', # removed this when gn is fixed
  'skia_use_system_libpng':        'true',
  'skia_use_system_jsoncpp':       'true',
  'skia_use_system_libwebp':       'true',
  'skia_use_system_libjpeg_turbo': 'true',
  'skia_use_system_zlib':          'true',
}

for (k,v) in SkqpGnArgs.iteritems():
    gn_args[k] = v

js = gn_to_bp_utils.GenerateJSONFromGN(gn_args)

def strip_slashes(lst):
  return {str(p.lstrip('/')) for p in lst}

srcs            = strip_slashes(js['targets']['//:libskqp_app']['sources'])
cflags          = strip_slashes(js['targets']['//:libskqp_app']['cflags'])
cflags_cc       = strip_slashes(js['targets']['//:libskqp_app']['cflags_cc'])
local_includes  = strip_slashes(js['targets']['//:libskqp_app']['include_dirs'])
defines      = {str(d) for d in js['targets']['//:libskqp_app']['defines']}

defines.update(["SK_ENABLE_DUMP_GPU", "SK_BUILD_FOR_SKQP"])
cflags_cc.update(['-Wno-extra-semi-stmt'])

gn_to_bp_utils.GrabDependentValues(js, '//:libskqp_app', 'sources', srcs, None)
gn_to_bp_utils.GrabDependentValues(js, '//:libskqp_app', 'include_dirs',
                                   local_includes, 'freetype')
gn_to_bp_utils.GrabDependentValues(js, '//:libskqp_app', 'defines',
                                   defines, None)

# No need to list headers or other extra flags.
srcs = {s for s in srcs           if not s.endswith('.h')}
cflags = gn_to_bp_utils.CleanupCFlags(cflags)
cflags_cc = gn_to_bp_utils.CleanupCCFlags(cflags_cc)

# We need to add the include path to the vulkan defines and header file set in
# then skia_vulkan_header gn arg that is used for framework builds.
local_includes.add("platform_tools/android/vulkan")

# Get architecture specific source files
defs = gn_to_bp_utils.GetArchSources(os.path.join(skia_gn_dir, 'opts.gni'))

# Add source file until fix lands in
# https://skia-review.googlesource.com/c/skia/+/101820
srcs.add("src/ports/SkFontMgr_empty_factory.cpp")

# Turn a list of strings into the style bpfmt outputs.
def bpfmt(indent, lst, sort=True):
  if sort:
    lst = sorted(lst)
  return ('\n' + ' '*indent).join('"%s",' % v for v in lst)

# Most defines go into SkUserConfig.h, where they're seen by Skia and its users.
gn_to_bp_utils.WriteUserConfig('include/config/SkUserConfig.h', defines)

# OK!  We have everything to fill in Android.bp...
with open('Android.bp', 'w') as f:
  print >>f, bp.substitute({
    'local_includes': bpfmt(8, local_includes),
    'srcs':           bpfmt(8, srcs),
    'cflags':         bpfmt(8, cflags, False),
    'cflags_cc':      bpfmt(8, cflags_cc),

    'arm_srcs':       bpfmt(16, defs['armv7']),
    'arm_neon_srcs':  bpfmt(20, defs['neon']),
    'arm64_srcs':     bpfmt(16, defs['arm64'] +
                                defs['crc32']),
    'none_srcs':      bpfmt(16, defs['none']),
    'x86_srcs':       bpfmt(16, defs['sse2'] +
                                defs['ssse3'] +
                                defs['sse41'] +
                                defs['sse42'] +
                                defs['avx'] +
                                defs['hsw']),
  })

