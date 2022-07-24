#!/usr/bin/env python3

import os
import gi
import sys
import uuid
import tempfile
import argparse

gi.require_version("Colord", "1.0")
from gi.repository import Colord, Gio

PROFILE_PREFIX = "lumi-"


def generate_vcgt(gamma, temperature, brightness):
    samples = 512
    gamma_factor = 1 / gamma

    colorbody = Colord.ColorRGB()
    Colord.color_get_blackbody_rgb(temperature, colorbody)
    colorbody = (colorbody.R, colorbody.G, colorbody.B)

    def vcg(i):
        coeff = ((i / (samples - 1)) ** gamma_factor)
        values = [brightness * coeff * cb for cb in colorbody]
        
        color = Colord.ColorRGB()
        color.set(*values)
        return color

    return [vcg(i) for i in range(samples)]


class Parser(argparse.ArgumentParser):
    def __init__(self):
        super().__init__()

        self.add_argument(
            "brightness",
            nargs="?",
            default="1",
            help="display brightness (1 by default)"
        )
        self.add_argument(
            "-d",
            "--display",
            type=int,
            default=0,
            help="display device index (0 by default)"
        )
        self.add_argument(
            "-g",
            "--gamma",
            default="1",
            help="target gamma correction (1 by default)"
        )
        self.add_argument(
            "-t",
            "--temperature",
            type=int,
            default=6500,
            help="target color temperature (6500 by default)"
        )

        if len(sys.argv) < 2:
            self.print_help()
            sys.exit(2)

    def parse(self):
        args = self.parse_args()
        args.gamma = float(args.gamma)
        args.temperature = float(args.temperature)
        args.brightness = max(min(float(args.brightness), 1), 0)
        return args


class ProfileMgr(Colord.Client):
    def __init__(self, device = 0):
        super().__init__()
        self.connect_sync()
        self.devices = self.get_display_devices()
        
        if device >= len(self.devices):
            exit(f"Display not found")

        self.display = self.devices[device]
        if not self.is_device_enabled():
            print("Enabling color management for device")
            self.set_device_enabled(True)

    def get_display_devices(self):
        all_devices = self.get_devices_sync()
        display_devices = []

        for device in all_devices:
            device.connect_sync()
            if device.get_kind() == Colord.DeviceKind.DISPLAY:
                display_devices.append(device)
        return display_devices

    def get_current_profile(self):
        profiles = self.display.get_profiles()
        profile = None

        if profiles:
            profile = profiles[0]
            profile.connect_sync()
        return profile

    def remove_profile(self, profile):
        if profile.get_filename():
            os.remove(profile.get_filename())

    def clone_profile_data(self, profile):
        return profile.load_icc(0)

    def new_profile_with_name(self, profile_data, new_name):
        tmp_path = os.path.join(tempfile.gettempdir(), new_name)
        profile_data.save_file(
            Gio.File.new_for_path(tmp_path),
            Colord.IccSaveFlags.NONE,
            None
        )

        try:
            new_profile = self.import_profile_sync(Gio.File.new_for_path(tmp_path))
        finally:
            os.remove(tmp_path)

        self.display.add_profile_sync(Colord.DeviceRelation.HARD, new_profile)
        new_profile.connect_sync()
        return new_profile

    def create_and_set_sRGB_profile(self):
        profile = self.find_profile_by_filename_sync("sRGB.icc")
        if not profile:
            return None

        self.display.add_profile_sync(Colord.DeviceRelation.HARD, profile)
        profile.connect_sync()
        return profile

    def make_profile_default(self, profile):
        self.display.make_profile_default_sync(profile)

    def is_device_enabled(self):
        return self.display.get_enabled()

    def set_device_enabled(self, enabled):
        self.display.set_enabled_sync(enabled)


def main():
    args = Parser().parse()
    mgr = ProfileMgr(args.display)

    base_profile = mgr.get_current_profile()
    if not base_profile:
        base_profile = mgr.create_and_set_sRGB_profile()
    base_profile_info = base_profile.get_filename() or base_profile.get_id()

    unique_id = str(uuid.uuid4())
    profile_data = mgr.clone_profile_data(base_profile)
    profile_data.add_metadata("uuid", unique_id) 
    profile_data.set_vcgt(generate_vcgt(args.gamma, args.temperature, args.brightness))

    mgr.make_profile_default(mgr.new_profile_with_name(profile_data, PROFILE_PREFIX + unique_id))
    if PROFILE_PREFIX in base_profile_info:
        mgr.remove_profile(base_profile)


if __name__ == "__main__":
    main()