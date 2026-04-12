# Day 44 Runbook (2026-05-28)

## Pre-flight (Gate 5)
- [ ] No outstanding export requests (grep inbox for "warmpath" + "export" in last 30 days)

## Final verification

```bash
gpg --decrypt warmpath_final_2026-04-28.dump.gpg > /tmp/final_test.dump
ls -la /tmp/final_test.dump
rm /tmp/final_test.dump
```

## Destroy
- [ ] Delete warmpath_final_2026-04-28.dump.gpg from 1Password
- [ ] Delete warmpath-final.bundle.gpg from 1Password
- [ ] Verify deletion in 1Password audit log
- [ ] Remove calendar reminder

## Done

Project has zero remaining PII liability. Nothing else to do.
