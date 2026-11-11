# Run 431 stall — evidence (tmo, tmox51322)

## Conclusion

UNLISTED. Readout group 0 is 100% dead because of XPM:2 link 6, which is HSD 3E:B. Someone
removed that HSD from the run by commenting `hsd_7` out of tmo.cnf. But the HSD itself is still
enabled, and its link still carries deadtime into group 0. No DRP reads it, so its buffers filled
up, it keeps pausing timing, and it holds deadtime at 1.0. None of the four playbook causes fits.
Its link is locked, its PGP lanes are up, the KCU write buffers are not stuck in hardware, and
deadtime is present, so it is not stuck_transitions. The target is not a segment in this run's
cnf, because `hsd_7` is commented out.

## 1. The XPM sees full deadtime from link 6 alone

> DAQ:NEH:XPM:2:PART:0:L0InpRate 2026-10-22 03:40:52.118  1020.4
> DAQ:NEH:XPM:2:PART:0:L0AccRate 2026-10-22 03:40:52.118  0
> DAQ:NEH:XPM:2:PART:0:DeadFrac 2026-10-22 03:40:52.118  1
> DAQ:NEH:XPM:2:PART:0:DeadFLnk 2026-10-22 03:40:52.118  [0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]

Link 6 is HSD 3E:B. Its timing link is locked with no errors, so this is not deadtime_link:

>    6  hsd 3E:B                    1          0     1.000

## 2. HSD 3E:B is enabled but nobody reads it, so its buffers are full and it pauses timing

> 3E:B        1       4/4        0       0      4123987

All 4 of its PGP lanes are up (4/4), so this is not hsd_link. Its remaining buffers are 0/0, and
its timing pause count is in the millions. Every other enabled HSD has 64 free events and a pause
count of 0.

## 3. It was removed from the cnf but not disabled at the HSD/XPM

> 03:31  hsd 3E:B noisy since run 425; commented hsd_7 out of tmo.cnf.
> #{host:'drp-srcf-cmp018', id:'hsd_7',  flags:'spu', env:hsd_epics_env, cmd:drp_cmd0+f' -D hsd -k hsd_epics_prefix={hsd_epics}_3E:B'},

Compare 1B:B. It is also commented out of the cnf, and it is correctly disabled (enable 0):

> #{host:'drp-srcf-cmp020', id:'hsd_1',  flags:'spu', env:hsd_epics_env, cmd:drp_cmd0+f' -D hsd -k hsd_epics_prefix={hsd_epics}_1B:B'},
> 1B:B        0       4/4       64    2048            0

## 4. The configured DRPs are healthy

> drp_deadtime{alias="hsd_5",detname="hsd",detseg="5",instrument="tmo",partition="0"} 0
> drp_deadtime{alias="tmo_atmopal_0",detname="tmo_atmopal",detseg="0",instrument="tmo",partition="0"} 0
> drp_dma_in_use{alias="timing_0",detname="timing",detseg="0",instrument="tmo",partition="0"} 0

Every configured segment reports deadtime 0. The KCU write buffers are queued in Pre-Hw, not
stuck in hardware, so this is not kcu_buffers:

>         Buffers In Hw : 0
>   Buffers In Pre-Hw Q : 4

The Disable failures follow from the run accepting nothing (0 Hz), so they are a symptom, not
the cause:

> 2026-10-22 03:41:02,921 tmo-control[3307]: <E> disable phase2 failed

## 5. Run 412's cause (link 4, drp-srcf-cmp026) is not involved this time

> DAQ:NEH:XPM:2:LinkRxReady4  2026-10-22 02:30:41.552  1
>    4  drp-srcf-cmp026             1          0     0.000

Link 4 has been locked since 02:30, and it shows no deadtime in run 431. The run 431 symptoms
look like run 412's, but here the deadtime comes from a different link (6, not 4).

## Suggestion (for the on-call person; nothing was changed)

Take HSD 3E:B out of readout group 0. Either set its enable to 0 in hsdpva
(DAQ:TMO:HSD:1_3E:B), the same way 1B:B is disabled, or remove XPM:2 link 6 from group 0 in
xpmpva. Then restartdaq. The other option is to restore `hsd_7` in tmo.cnf so a DRP reads it.
That would bring the noisy channel back.
