#!/usr/bin/env python3
"""Finder'a "Mühürle" Hızlı Eylemi kurar."""

import plistlib
import uuid
from pathlib import Path

AD = "Mühürle"
KOK = Path.home() / "Library/Services" / f"{AD}.workflow"
ICERIK = KOK / "Contents"
ICERIK.mkdir(parents=True, exist_ok=True)

KOMUT = (
    'cd "$HOME/Muhur" || exit 1\n'
    'for f in "$@"; do\n'
    '  ./venv/bin/python imzala-hizli.py "$f"\n'
    'done\n'
)

eylem = {
    "action": {
        "AMAccepts": {
            "Container": "List",
            "Optional": True,
            "Types": ["com.apple.cocoa.string"],
        },
        "AMActionVersion": "2.0.3",
        "AMApplication": ["Automator"],
        "AMParameterProperties": {
            "COMMAND_STRING": {},
            "CheckedForUserDefaultShell": {},
            "inputMethod": {},
            "shell": {},
            "source": {},
        },
        "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
        "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
        "ActionName": "Run Shell Script",
        "ActionParameters": {
            "COMMAND_STRING": KOMUT,
            "CheckedForUserDefaultShell": True,
            "inputMethod": 1,  # girdiyi argüman olarak ver
            "shell": "/bin/zsh",
            "source": "",
        },
        "BundleIdentifier": "com.apple.RunShellScript",
        "CFBundleVersion": "2.0.3",
        "CanShowSelectedItemsWhenRun": False,
        "CanShowWhenRun": True,
        "Category": ["AMCategoryUtilities"],
        "Class Name": "RunShellScriptAction",
        "InputUUID": str(uuid.uuid4()),
        "OutputUUID": str(uuid.uuid4()),
        "UUID": str(uuid.uuid4()),
        "UnlocalizedApplications": ["Automator"],
        "arguments": {},
        "isViewVisible": 1,
        "location": "309.000000:253.000000",
        "nibPath": (
            "/System/Library/Automator/Run Shell Script.action"
            "/Contents/Resources/Base.lproj/main.nib"
        ),
    },
    "isViewVisible": 1,
}

wflow = {
    "AMApplicationBuild": "521",
    "AMApplicationVersion": "2.10",
    "AMDocumentVersion": "2",
    "actions": [eylem],
    "connectors": {},
    "workflowMetaData": {
        "serviceInputTypeIdentifier": "com.apple.Automator.fileSystemObject",
        "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
        "serviceApplicationBundleID": "com.apple.finder",
        "serviceApplicationName": "Finder",
        "serviceProcessesInput": 0,
        "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        "presentationMode": 3,  # Hızlı Eylem olarak göster
    },
}

info = {
    "NSServices": [
        {
            "NSMenuItem": {"default": AD},
            "NSMessage": "runWorkflowAsService",
            "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
            "NSSendFileTypes": ["com.adobe.pdf"],
        }
    ]
}

with open(ICERIK / "document.wflow", "wb") as f:
    plistlib.dump(wflow, f)
with open(ICERIK / "Info.plist", "wb") as f:
    plistlib.dump(info, f)

print("kuruldu:", KOK)
