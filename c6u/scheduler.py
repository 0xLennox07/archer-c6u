"""Generate a Windows Task Scheduler XML to run `c6u daemon` at logon."""
from __future__ import annotations

import sys
from pathlib import Path

XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>c6u router daemon — snapshots, latency, public IP, webhooks, MQTT</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <Enabled>true</Enabled>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>5</Count>
    </RestartOnFailure>
  </Settings>
  <Actions>
    <Exec>
      <Command>{python}</Command>
      <Arguments>"{script}" daemon</Arguments>
      <WorkingDirectory>{cwd}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def emit_xml(out: Path) -> Path:
    cwd = Path(__file__).resolve().parent.parent
    xml = XML_TEMPLATE.format(
        python=sys.executable.replace("&", "&amp;"),
        script=str(cwd / "main.py").replace("&", "&amp;"),
        cwd=str(cwd).replace("&", "&amp;"),
    )
    # Task Scheduler wants UTF-16 LE with BOM
    out.write_bytes(b"\xff\xfe" + xml.encode("utf-16-le"))
    return out
