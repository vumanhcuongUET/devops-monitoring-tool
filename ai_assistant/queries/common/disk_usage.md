# Disk Usage Query

## Query ID
`disk_usage`

## Description
Displays disk usage metrics across all nodes including disk used percentage, available space, inode usage, and I/O rates.

## Output Format

### Disk Used % (≥70% shown)
| Host | Mountpoint | Disk % | Status |
|------|------------|--------|--------|
| server1 | / | 75% | ⚠️ |
| server2 | /var | 92% | 🔴 |

**Highlight rules:**
- ⚠️ 70% or higher
- 🔴 85% or higher

### Available GB (<10GB warned)
| Host | Mountpoint | Available GB |
|------|------------|--------------|
| server1 | / | 8.2 GB |

**Highlight rules:**
- ⚠️ Less than 10GB
- 🔴 Less than 5GB

### Inodes Free % (<20% shown)
| Host | Mountpoint | Inodes % | Status |
|------|------------|----------|--------|
| server1 | /var | 15% | ⚠️ |

**Highlight rules:**
- ⚠️ 15% or less
- 🔴 5% or less

### Disk I/O Rate (≥50MB/s shown)
| Host | Device | IO Rate |
|------|--------|---------|
| server1 | sda | 62.5 MB/s |

**Highlight rules:**
- ⚠️ 50MB/s or higher
- 🔴 100MB/s or higher

## Example Usage

```bash
python tools/run_query_v2.py --project meinvoice --section disk_usage
python tools/run_query_v2.py --project meinvoice --section disk_usage --time-range now-30m
```

## Troubleshooting Tips

### High Disk Usage (≥70%)
- Clean old logs: `find /var/log -name '*.log' -mtime +30 -delete`
- Find large files: `du -sh /* 2>/dev/null | sort -hr | head -10`
- Consider expanding disk size or implementing log rotation

### Low Available Space (<10GB)
- Plan disk expansion immediately
- Move backups to external storage
- Clean up temporary files and caches

### Inode Exhaustion
- Find directories with many files: `find / -type d -exec sh -c 'echo "{}:"; find "{}" -type f | wc -l' \; | sort -t: -k2 -rn`
- Clean up small files: `find /tmp -type f -atime +7 -delete`

### High I/O Rates
- Check processes: `iotop` or `iostat -x 1`
- For databases: Review query optimization and checkpoint settings
- For applications: Consider reducing log verbosity or frequency

## See Also
- `node_memory_detail.yaml` - Memory usage details
- `node_linux_status.yaml` - Overall node health summary
