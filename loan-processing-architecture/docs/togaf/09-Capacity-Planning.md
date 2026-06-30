# Back-of-the-Envelope Capacity Planning

## Baseline Assumptions
- Registered users: 500,000
- Daily loan applications: 100,000
- Peak traffic multiplier: 10x average
- Average submit payload: 5 KB
- Average status response: 1 KB
- Average RabbitMQ event: 2 KB
- Average Redis status entry: 1 KB

## TPS Calculation
Average loan submit TPS:
```text
100,000 / 86,400 = 1.15 TPS
Peak = 1.15 * 10 = ~12 TPS
```

Enterprise scale assumption:
```text
2,000,000 applications/day / 86,400 = 23 TPS average
Peak = 23 * 10 = ~230 TPS
```

## Status Lookup TPS
If each applicant checks status 10 times/day:
```text
100,000 * 10 = 1,000,000 reads/day
1,000,000 / 86,400 = 11.5 TPS average
Peak = ~115 TPS
```
This makes the status API read-heavy.

## Redis Memory
```text
1 KB/status * 500,000 active applications = ~500 MB
With overhead and replication, plan 1.5 GB to 2 GB
```

## RabbitMQ Throughput
```text
2 KB/event * 230 TPS peak = 460 KB/sec
With 3 consumers, logical fan-out traffic is ~1.4 MB/sec
```

## Storage Estimate
If each loan row is 2 KB:
```text
10 million loans * 2 KB = ~20 GB
```
If documents average 5 MB and 200,000 documents/day:
```text
5 MB * 200,000 = ~1 TB/day
365 TB/year before compression/lifecycle policies
```

## Bottlenecks
- Document storage and verification pipeline.
- External credit bureau latency.
- RabbitMQ queue growth during consumer outage.
- Database writes for high submit traffic.
