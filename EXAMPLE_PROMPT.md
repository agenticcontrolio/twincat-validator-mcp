# Example Prompt — Dual-Tank Transfer and Dosing System

A complete worked prompt for planning and implementing a TwinCAT 3 subsystem.
It follows the **plan → approve → implement → validate** pattern — see the
[Recommended Workflow](README.md#recommended-workflow) diagrams in the README.

Copy and adapt this prompt for your own tasks. Adjust the requirements section
to match your process.

---

```
Before writing any code, analyze the task below and produce a single Markdown
file (PLAN_DualTank_TwinCAT.md) that contains:

- A clear list of requirements derived from the task
- The artifacts to be created (files, types, purpose)
- Validation and acceptance criteria that the implementation must satisfy
- A sequenced TODO list of implementation steps

Keep the plan professional, complete, and as simple as possible. Once the file
is created, stop and wait for the user to review and approve before writing any
code or TwinCAT files.

---

Plan first and design and implement after a TwinCAT 3 subsystem for a
dual-tank transfer and dosing process with strict safety and recovery behavior.

**Requirements:**

Create a control program that manages:
- Tank A level control (source tank)
- Tank B level control (destination tank)
- Transfer pump with soft-start behavior
- Dosing valve for additive injection into Tank B
- Drain valve for emergency relief in Tank B

**Inputs/Signals to model:**
- bStart, bStop, bReset
- bEStop
- bPumpFeedback
- bLowLevelA, bHighLevelA
- bLowLevelB, bHighLevelB
- rFlowLpm (flow sensor)
- rPressureBar (line pressure)
- bValveDoseFeedback
- bValveDrainFeedback

**Outputs/Commands:**
- bPumpCmd
- bValveDoseCmd
- bValveDrainCmd
- bAlarmGeneral
- nFaultCode
- rBatchTotalLiters

**Behavior:**
- On start, verify permissives before enabling transfer.
- Transfer must stop if Tank A low level or Tank B high level is reached.
- Dosing valve should pulse based on transferred volume (e.g., every 25 L,
  dose for configurable time).
- If pressure exceeds a high threshold, immediately stop pump and open drain valve.
- If actuator feedback does not confirm command within timeout, raise fault.
- Include debounce/filter logic for noisy level switches.
- Include a watchdog timer for "pump commanded but no flow detected".

**Fault handling:**
- Distinguish at least 6 specific fault codes.
- Latch faults until reset.
- Reset only allowed when all unsafe conditions are cleared.
- After reset, system returns to idle safely (all actuators off).

**Diagnostics:**
- Keep counters for starts, completed batches, aborted batches, and fault occurrences.
- Track last fault timestamp (cycle counter-based is fine).
- Provide a compact status word/bitfield for HMI.

**Constraints:**
- Keep it in a small set of TwinCAT artifacts (program + needed DUT/GVL if useful).
- Must pass strict validation/import/compile checks.
- Deterministic behavior over repeated validation/autofix runs.
```
