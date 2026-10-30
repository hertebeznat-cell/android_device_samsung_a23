# SPDX-License-Identifier: Apache-2.0
#
# OTA extensions for the Galaxy A23 4G.
#
# vendor is the prebuilt stock SEZB1 image, so target-files has no VENDOR/
# tree and the generic non-A/B script would skip it while it is still listed
# in the super group. Provide its block update here: every install then
# writes the exact stock vendor, whatever the phone had before (UN1CA, for
# example, repacks vendor). odm is built and handled by the generic script.

import common

STOCK_PARTITIONS = ('vendor',)


class _FullSuperLayout(common.DynamicPartitionsDifference):
  """Recreates the whole super layout on full installs.

  Lineage's non-A/B script sees no VENDOR/ tree, takes this for a system-only
  build and emits only "resize" ops, keeping the phone's existing partitions.
  A phone coming from UN1CA has no product partition, so the install aborted
  ("Failed to find partition product in dynamic partition metadata"). vendor
  and odm are always written here, so the AOSP full-OTA layout is correct.
  """

  def __init__(self, *args, **kwargs):
    kwargs['build_without_vendor'] = False
    super().__init__(*args, **kwargs)


# This module is loaded before the non-A/B script builds its op list.
if not getattr(common.DynamicPartitionsDifference, 'a23_full_layout', False):
  _FullSuperLayout.a23_full_layout = True
  common.DynamicPartitionsDifference = _FullSuperLayout


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
