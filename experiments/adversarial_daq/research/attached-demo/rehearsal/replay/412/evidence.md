# Run 412 stall — evidence

**Diagnosis:** deadtime_link on `tmo_atmopal_0` (drp-srcf-cmp026). The timing link from cmp026 back to XPM:2 (link 4) has lost lock, so the XPM sees permanent deadtime from it. Readout group 0 is therefore 100% dead and L0 accepts are 0.

## 1. The XPM sees full deadtime, and all of it comes from link 4

The input rate is normal, but nothing is accepted:

> DAQ:NEH:XPM:2:PART:0:L0InpRate 2026-10-22 02:13:40.004  1020.4

> DAQ:NEH:XPM:2:PART:0:L0AccRate 2026-10-22 02:13:40.004  0

> DAQ:NEH:XPM:2:PART:0:DeadFrac 2026-10-22 02:13:40.004  1

In the per-link deadtime array, only index 4 is set:

> DAQ:NEH:XPM:2:PART:0:DeadFLnk 2026-10-22 02:13:40.004  [0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]

## 2. Link 4 is drp-srcf-cmp026, and its receiver has no lock

Link 4 has RxReady 0 and its error counter is saturated. Every other link is ready, has no errors and shows no deadtime:

> link  remote            LinkRxReady  LinkRxErr  DeadFLnk

>    4  drp-srcf-cmp026             0      65535     1.000

## 3. The link dropped just after the camlink work and again after the run started

> DAQ:NEH:XPM:2:LinkRxReady4  2026-10-22 02:00:00.000  1

> DAQ:NEH:XPM:2:LinkRxReady4  2026-10-22 02:10:31.027  0

> DAQ:NEH:XPM:2:LinkRxReady4  2026-10-22 02:10:31.904  1

> DAQ:NEH:XPM:2:LinkRxReady4  2026-10-22 02:12:50.311  0

These times line up with the shift log:

> 02:09  swapped the camlink cable at the opal's camlink box (intermittent frames).

> 02:12  run 412 started, recording.

> 02:13  accepted rate 0 Hz, deadtime 100% in grafana. Disable hangs. Paging DAQ on-call.

## 4. cmp026 is the tmo_atmopal_0 segment

> { host: 'drp-srcf-cmp026', id:'tmo_atmopal_0', flags:'spu', env:epics_env, cmd:drp_cmd0+' -l 0x1 -D opal -k ttpv=TMO:TIMETOOL:TTALL'},

In the DRP metrics, it is the only segment reporting deadtime:

> drp_deadtime{alias="tmo_atmopal_0",detname="tmo_atmopal",detseg="0",instrument="tmo",partition="0"} 1

## 5. The other three playbook causes are ruled out

- **kcu_buffers:** On cmp026 all 1024 read buffers are in hardware and none are in user space. The write buffers are queued in Pre-Hw, not stuck in hardware. cmp007 and cmp028 look the same. DMA in use is 0 everywhere, including:

> drp_dma_in_use{alias="tmo_atmopal_0",detname="tmo_atmopal",detseg="0",instrument="tmo",partition="0"} 0

- **hsd_link:** Every HSD side shows `4/4` lanes up with full free buffers. The HSD XPM links are all RxReady=1 with no errors.
- **stuck_transitions:** This needs "no deadtime", but DeadFrac is 1 and is attributed to link 4. The disable failure follows from the dead link: no triggers or transitions can get through the stalled group.

> 2026-10-22 02:13:44,921 tmo-control[2201]: <E> disable phase2 failed

## Recommended fix (on-call to carry out; nothing was changed here)

1. Check and reseat the timing fiber between drp-srcf-cmp026's KCU and XPM:2 link 4. It may have been disturbed during the 02:09 camlink work at the opal.
2. Confirm that `DAQ:NEH:XPM:2:LinkRxReady4` returns to 1 and stays there, and that LinkRxErr4 stops counting.
3. If the link does not relock, reset or re-init the KCU timing link on cmp026.
4. Run restartdaq and start a new run.
