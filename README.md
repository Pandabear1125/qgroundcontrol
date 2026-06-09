# Custom Readme
Install the deps on macos and build for the first time with the install.sh script. Compile new changes with the compile.sh script.

NOTE: every recompile will make mac reprompt for permission requests fyi

## Mach MAVLink generation

This fork defaults QGC to the `qgc_mach` dialect, but the generated MAVLink C headers are not committed. Generate them locally at `libs/mavlink/include/mavlink/v2.0` before configuring or building QGC.

The generated header directory is ignored by git so custom MAVLink headers do not land in the public fork. Regenerate the local headers after cloning this branch and whenever the firmware MAVLink XML changes. PX4 firmware is the source of truth: first check out the PX4 repo at the firmware branch or commit you want to use, then run the generator. It builds `qgc_mach` from PX4 `all.xml` plus `mach.xml` in the PX4 MAVLink XML directory.

```sh
python3 tools/generate_qgc_mach_mavlink.py --px4-repo /path/to/px4
```

By default, the generator uses the supplied PX4 repo's `HEAD`, reads `mach.xml`, and writes the `qgc_mach` dialect. To use a different dialect name:

```sh
python3 tools/generate_qgc_mach_mavlink.py --px4-repo /path/to/px4 --dialect <dialect-name>
```

Then verify the generated tree:

```sh
python3 tools/verify_qgc_mach_mavlink.py
```

The verifier checks the generated message IDs, names, lengths, CRC extras, message-info table entries, and manifest. If you need to generate with a specific mavgen executable, pass `--mavgen-cmd` or set `MAVGEN_CMD`.

QGC defaults to `qgc_mach` for both CMake and qmake. Configure/build will fail if the generated headers are missing. For CMake overrides, use `QGC_MAVLINK_ROOT` and `QGC_MAVLINK_DIALECT`; for qmake overrides, keep using `MAVLINKPATH_REL`, `MAVLINKPATH`, and `MAVLINK_CONF`.


# QGroundControl Ground Control Station (old)

[![Releases](https://img.shields.io/github/release/mavlink/QGroundControl.svg)](https://github.com/mavlink/QGroundControl/releases)

*QGroundControl* (QGC) is an intuitive and powerful ground control station (GCS) for UAVs.

The primary goal of QGC is ease of use for both first time and professional users.
It provides full flight control and mission planning for any MAVLink enabled drone, and vehicle setup for both PX4 and ArduPilot powered UAVs. Instructions for *using QGroundControl* are provided in the [User Manual](https://docs.qgroundcontrol.com/en/) (you may not need them because the UI is very intuitive!)

All the code is open-source, so you can contribute and evolve it as you want.
The [Developer Guide](https://dev.qgroundcontrol.com/en/) explains how to [build](https://dev.qgroundcontrol.com/en/getting_started/) and extend QGC.


Key Links:
* [Website](http://qgroundcontrol.com) (qgroundcontrol.com)
* [User Manual](https://docs.qgroundcontrol.com/en/)
* [Developer Guide](https://dev.qgroundcontrol.com/en/)
* [Discussion/Support](https://docs.qgroundcontrol.com/en/Support/Support.html)
* [Contributing](https://dev.qgroundcontrol.com/en/contribute/)
* [License](https://github.com/mavlink/qgroundcontrol/blob/master/COPYING.md)
