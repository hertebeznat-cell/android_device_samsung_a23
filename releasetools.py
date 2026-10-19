# SPDX-License-Identifier: Apache-2.0
#
# OTA extensions for the Galaxy A23 4G.
#
# vendor and odm are prebuilt stock SEZB1 images, so target-files has no
# VENDOR/ or ODM/ trees and the generic non-A/B script would skip them while
# they are still listed in the super group. Provide their block updates here:
# every install then writes the exact stock vendor/odm, whatever the phone
# had before (UN1CA, for example, repacks vendor).

import common

STOCK_PARTITIONS = ('vendor', 'odm')


def FullOTA_GetBlockDifferences(info):
  return [_StockImage(info, partition) for partition in STOCK_PARTITIONS]


def IncrementalOTA_GetBlockDifferences(info):
  # Incremental packages are not supported for these prebuilt images.
  return None


def FullOTA_InstallEnd(info):
  # Stock SEZB1 DTBO, matching the DTB in boot.img.
  for name in ('IMAGES/dtbo.img', 'PREBUILT_IMAGES/dtbo.img'):
    if name in info.input_zip.namelist():
      common.ZipWriteStr(info.output_zip, 'dtbo.img', info.input_zip.read(name))
      info.script.Print('Flashing stock dtbo...')
      info.script.WriteRawImage('/dtbo', 'dtbo.img')
      return
  raise ValueError('dtbo.img missing from target-files')


def _StockImage(info, partition):
  image = common.GetUserImage(partition, info.input_tmp, info.input_zip,
                              info_dict=info.info_dict, reset_file_map=True)
  return common.BlockDifference(partition, image, src=None)
