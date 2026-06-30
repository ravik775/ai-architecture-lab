# Redis for Solution Architects

## What is Redis?

Redis (Remote Dictionary Server) is an in-memory data structure store used as:

* Cache
* Key-Value Store
* Distributed Lock Manager
* Session Store
* Message Broker
* Stream Processing Engine
* Real-Time Analytics Store

Unlike traditional databases, Redis keeps data primarily in memory, delivering sub-millisecond response times.

```text
Application
     |
     v
   Redis
     |
     v
 Memory
```

---

# Useful Redis URLs

Redis itself does not provide a native web administration console.

## RedisInsight (Recommended)

Official GUI from Redis.

Official Site:

[Redis Insight](https://redis.io/insight/?utm_source=chatgpt.com)

Default URL after installation:

```text
http://localhost:5540
```

---

## Redis Commander

Web UI for Redis.

Official Repository:

[Redis Commander GitHub](https://github.com/joeferner/redis-commander?utm_source=chatgpt.com)

Docker:

```bash
docker run -d \
  --name redis-commander \
  -p 8081:8081 \
  rediscommander/redis-commander
```

Access:

```text
http://localhost:8081
```

---

## Redis CLI

Connect to Redis container:

```bash
docker exec -it redis redis-cli
```

Useful commands:

```bash
PING
```

```bash
KEYS *
```

```bash
GET customer:123
```

```bash
INFO
```

---

# Redis Architecture

```text
Application
      |
      v
   Redis
      |
      +--> Memory
      |
      +--> Optional Persistence
```

Redis prioritizes speed through memory-based storage.

---

# PACELC Analysis of Redis

## CAP Perspective

Redis can operate in multiple modes.

### Standalone Redis

```text
Single Node
```

No distributed consistency concerns.

---

### Redis Replication

```text
Master
  |
  +--> Replica1
  |
  +--> Replica2
```

Replication is asynchronous.

---

# PACELC Classification

For standard Redis replication:

```text
PA/EL
```

Meaning:

```text
Partition:
    Availability preferred

Else:
    Latency preferred
```

Reason:

* Asynchronous replication
* Writes acknowledged before replicas confirm
* Extremely low latency

---

# Example

```text
Client
   |
Write
   |
Master
   |
ACK Client
   |
Replicate Later
```

Benefits:

* Very low latency

Tradeoff:

* Possible data loss during failover

---

# Stronger Consistency with Redis

Redis offers mechanisms to move toward consistency.

---

## WAIT Command

```bash
WAIT 2 1000
```

Meaning:

```text
Wait until 2 replicas confirm
or timeout after 1000 ms
```

Benefits:

* Better consistency

Tradeoff:

* Increased latency

PACELC:

```text
EC
```

---

## Redis Sentinel

Provides:

```text
Monitoring
Failover
Leader Election
```

Architecture:

```text
Sentinel
    |
Master
   / \
 R1  R2
```

---

## Redis Cluster

```text
Shard1
Shard2
Shard3
```

Benefits:

* Horizontal scaling
* Automatic partitioning

Tradeoff:

* Eventual consistency across replicas

---

# Consistency Characteristics

## Read Consistency

Possible scenario:

```text
Write Master
Read Replica
```

Replica may lag.

Result:

```text
Stale Read
```

Redis replication is eventually consistent.

---

## Write Consistency

Write is committed to primary first.

```text
Client
  |
Primary
```

Acknowledged immediately.

Replication occurs afterward.

---

# Redis Data Structures

## String

```bash
SET loan:100 APPROVED
```

---

## Hash

```bash
HSET customer:1
 name Ravi
 age 35
```

---

## List

```bash
LPUSH notifications msg1
```

---

## Set

```bash
SADD roles ADMIN
```

---

## Sorted Set

```bash
ZADD leaderboard 100 user1
```

---

## Stream

```bash
XADD orders *
```

Used for event streaming.

---

# Redis Persistence

## RDB Snapshot

```text
Memory
   |
Snapshot
   |
Disk
```

Benefits:

* Fast recovery

Tradeoff:

* Possible data loss between snapshots

---

## AOF (Append Only File)

```text
Write
  |
Log
  |
Disk
```

Benefits:

* Better durability

Tradeoff:

* Slightly higher latency

---

# Redis High Availability

## Sentinel

Provides:

* Monitoring
* Failover
* Leader election

Architecture:

```text
Sentinel
      |
 Primary
   /     \
Replica Replica
```

---

## Redis Cluster

Provides:

* Sharding
* Replication
* Failover

Architecture:

```text
Shard 1
Shard 2
Shard 3
```

---

# Enterprise Integration Patterns Supported by Redis

Redis is not a traditional integration broker like RabbitMQ, but it supports several messaging and integration patterns.

---

## Publish-Subscribe

```text
Publisher
     |
 Redis Channel
     |
Subscriber A
Subscriber B
```

Commands:

```bash
PUBLISH
SUBSCRIBE
```

---

## Event Notification

```text
Application
      |
      v
Redis Channel
      |
Consumers
```

Suitable for:

* Cache invalidation
* User notifications

---

## Message Channel

```text
Producer
   |
Redis List
   |
Consumer
```

Using:

```bash
LPUSH
BRPOP
```

---

## Work Queue

```text
Producer
    |
 Redis Queue
    |
Workers
```

Pattern:

```bash
LPUSH
BRPOP
```

---

## Stream Processing

```text
Producer
   |
 Redis Stream
   |
 Consumer Group
```

Commands:

```bash
XADD
XREADGROUP
```

Comparable to lightweight Kafka-like processing.

---

## Fan-Out Pattern

```text
Publisher
   |
 Redis Pub/Sub
  /  |  \
 A   B   C
```

---

## Competing Consumers

```text
Queue
 |
 +--> Worker1
 +--> Worker2
 +--> Worker3
```

Implemented via:

```text
Lists
Streams
Consumer Groups
```

---

# Redis vs RabbitMQ

| Feature                         | Redis              | RabbitMQ       |
| ------------------------------- | ------------------ | -------------- |
| Primary Purpose                 | Cache & Data Store | Message Broker |
| Latency                         | Extremely Low      | Low            |
| Persistence                     | Optional           | Strong         |
| Routing                         | Basic              | Advanced       |
| Transactions                    | Limited            | Limited        |
| Message Ordering                | Stream Based       | Queue Based    |
| Pub/Sub                         | Yes                | Yes            |
| Enterprise Integration Patterns | Moderate           | Extensive      |
| Event Streaming                 | Streams            | Limited        |
| Caching                         | Excellent          | No             |

---

# Architect Best Practices

## Use Redis For

* Caching
* Session Management
* Distributed Locks
* Rate Limiting
* Real-Time Counters
* Feature Flags
* Leaderboards
* Streams

---

## Avoid Redis For

* Financial Transactions
* Guaranteed Delivery Messaging
* Long-Term Event Retention
* Complex Message Routing

Use RabbitMQ or Kafka instead.

---

# Interview Answer

### What PACELC consistency model does Redis provide?

Standard Redis replication is generally:

```text
PA/EL
```

Because:

* During partitions, availability is preferred.
* Under normal operation, latency is preferred over strong consistency.
* Replication is asynchronous.
* Reads from replicas can be stale.
* Failover can result in small amounts of data loss.

Redis can move closer to consistency using:

* WAIT
* Sentinel
* Cluster
* AOF Persistence

but its primary design goal remains extremely low latency rather than strict distributed consistency.
