package org.ex.apigateway.service;

import io.github.bucket4j.BucketConfiguration;
import io.github.bucket4j.ConsumptionProbe;
import io.github.bucket4j.distributed.AsyncBucketProxy;
import io.github.bucket4j.distributed.proxy.AsyncProxyManager;
import io.github.bucket4j.distributed.proxy.ProxyManager;
import io.github.bucket4j.distributed.proxy.RemoteAsyncBucketBuilder;
import org.ex.apigateway.model.RateLimitResult;
import org.ex.apigateway.model.TenantPolicy;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;

import java.lang.reflect.Field;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * Proves the M5 fix with real concurrency, not just code inspection: N
 * requests that all miss the local lease at the same instant must trigger
 * exactly ONE call to the global (Redis-backed) bucket, not N calls each
 * independently drawing a full leaseSize batch.
 *
 * The Bucket4j proxy chain (ProxyManager -> AsyncProxyManager ->
 * RemoteAsyncBucketBuilder -> AsyncBucketProxy) is mocked; the mocked
 * tryConsumeAndReturnRemaining call is made to genuinely block (via a
 * CompletableFuture completed on a background thread, gated by a latch the
 * test controls) so the race window is real and deterministic rather than
 * relying on all-in-memory calls happening to interleave.
 */
class TenantLeaseServiceTest {

    private final ExecutorService bucketExecutor = Executors.newCachedThreadPool();
    private ExecutorService requestPool;

    @AfterEach
    void tearDown() {
        bucketExecutor.shutdownNow();
        if (requestPool != null) {
            requestPool.shutdownNow();
        }
    }

    @SuppressWarnings("unchecked")
    @Test
    void concurrentMissesForSameTenant_shareOneGlobalLease_insteadOfOneEach() throws Exception {
        String tenantId = "tenant-a";
        long leaseSize = 3;
        int concurrentRequests = 10;

        TenantPolicy policy = new TenantPolicy();
        policy.setTenantId(tenantId);
        policy.setRequestsPerMinute(1000);
        policy.setBurstCapacity(1000);

        TenantPolicyService policyService = mock(TenantPolicyService.class);
        when(policyService.getPolicy(tenantId)).thenReturn(Mono.just(policy));

        ProxyManager<String> proxyManager = mock(ProxyManager.class);
        AsyncProxyManager<String> asyncProxyManager = mock(AsyncProxyManager.class);
        RemoteAsyncBucketBuilder<String> builder = mock(RemoteAsyncBucketBuilder.class);
        AsyncBucketProxy bucketProxy = mock(AsyncBucketProxy.class);

        when(proxyManager.asAsync()).thenReturn(asyncProxyManager);
        when(asyncProxyManager.builder()).thenReturn(builder);
        when(builder.build(anyString(), any(Supplier.class))).thenReturn(bucketProxy);

        AtomicInteger globalBucketInvocations = new AtomicInteger(0);
        CountDownLatch firstCallStarted = new CountDownLatch(1);
        CountDownLatch releaseGlobalCall = new CountDownLatch(1);

        when(bucketProxy.tryConsumeAndReturnRemaining(anyLong())).thenAnswer(invocation -> {
            globalBucketInvocations.incrementAndGet();
            firstCallStarted.countDown();
            return CompletableFuture.supplyAsync(() -> {
                try {
                    // Held open deliberately: every concurrent request that
                    // misses its local lease while this is pending must join
                    // THIS in-flight call rather than starting a new one.
                    releaseGlobalCall.await(5, TimeUnit.SECONDS);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                return ConsumptionProbe.consumed(leaseSize, 0);
            }, bucketExecutor);
        });

        TenantLeaseService service = new TenantLeaseService(policyService, proxyManager);
        setLeaseSize(service, leaseSize);

        requestPool = Executors.newFixedThreadPool(concurrentRequests);
        CountDownLatch ready = new CountDownLatch(concurrentRequests);
        CountDownLatch go = new CountDownLatch(1);
        List<RateLimitResult> results = new CopyOnWriteArrayList<>();

        for (int i = 0; i < concurrentRequests; i++) {
            requestPool.submit(() -> {
                ready.countDown();
                try {
                    go.await();
                    results.add(service.consume(tenantId).block(Duration.ofSeconds(10)));
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
        }

        assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
        go.countDown();

        // Confirm the single in-flight call has actually started before
        // releasing it, so every one of the 10 requests above has had the
        // chance to pile onto it rather than the test racing ahead of them.
        assertThat(firstCallStarted.await(5, TimeUnit.SECONDS)).isTrue();
        Thread.sleep(300);
        releaseGlobalCall.countDown();

        requestPool.shutdown();
        assertThat(requestPool.awaitTermination(10, TimeUnit.SECONDS)).isTrue();

        assertThat(results).hasSize(concurrentRequests);
        assertThat(globalBucketInvocations.get())
                .as("global bucket must be drawn from exactly once for one batch of concurrent local misses")
                .isEqualTo(1);

        long allowedCount = results.stream().filter(RateLimitResult::allowed).count();
        assertThat(allowedCount)
                .as("exactly leaseSize tokens were granted by the single shared lease, so exactly that many requests should succeed")
                .isEqualTo(leaseSize);
        assertThat(results.stream().filter(r -> !r.allowed()).count()).isEqualTo(concurrentRequests - leaseSize);
    }

    @SuppressWarnings("unchecked")
    @Test
    void rejectedGlobalLease_reportsFloorOfOneRetryAfter_toEveryWaiter() throws Exception {
        // A second scenario for the same coalescing path: when the shared
        // lease itself is rejected (global bucket empty), every waiter that
        // shared it - not just the one that happened to trigger the call -
        // must get a sane, non-zero Retry-After.
        String tenantId = "tenant-b";
        long leaseSize = 2;
        int concurrentRequests = 5;

        TenantPolicy policy = new TenantPolicy();
        policy.setTenantId(tenantId);
        policy.setRequestsPerMinute(1000);
        policy.setBurstCapacity(1000);

        TenantPolicyService policyService = mock(TenantPolicyService.class);
        when(policyService.getPolicy(tenantId)).thenReturn(Mono.just(policy));

        ProxyManager<String> proxyManager = mock(ProxyManager.class);
        AsyncProxyManager<String> asyncProxyManager = mock(AsyncProxyManager.class);
        RemoteAsyncBucketBuilder<String> builder = mock(RemoteAsyncBucketBuilder.class);
        AsyncBucketProxy bucketProxy = mock(AsyncBucketProxy.class);

        when(proxyManager.asAsync()).thenReturn(asyncProxyManager);
        when(asyncProxyManager.builder()).thenReturn(builder);
        when(builder.build(anyString(), any(Supplier.class))).thenReturn(bucketProxy);

        // Rejected with 400ms left to refill - the exact H3 scenario,
        // reused here to confirm the coalesced path also floors to 1s.
        when(bucketProxy.tryConsumeAndReturnRemaining(anyLong()))
                .thenReturn(CompletableFuture.completedFuture(
                        ConsumptionProbe.rejected(0, 400_000_000L, 400_000_000L)));

        TenantLeaseService service = new TenantLeaseService(policyService, proxyManager);
        setLeaseSize(service, leaseSize);

        requestPool = Executors.newFixedThreadPool(concurrentRequests);
        CountDownLatch ready = new CountDownLatch(concurrentRequests);
        CountDownLatch go = new CountDownLatch(1);
        List<RateLimitResult> results = new CopyOnWriteArrayList<>();

        for (int i = 0; i < concurrentRequests; i++) {
            requestPool.submit(() -> {
                ready.countDown();
                try {
                    go.await();
                    results.add(service.consume(tenantId).block(Duration.ofSeconds(10)));
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
        }

        assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
        go.countDown();
        requestPool.shutdown();
        assertThat(requestPool.awaitTermination(10, TimeUnit.SECONDS)).isTrue();

        assertThat(results).hasSize(concurrentRequests);
        assertThat(results).allMatch(r -> !r.allowed());
        assertThat(results).allMatch(r -> r.retryAfterSeconds() == 1);
    }

    private static void setLeaseSize(TenantLeaseService service, long value) throws Exception {
        Field field = TenantLeaseService.class.getDeclaredField("leaseSize");
        field.setAccessible(true);
        field.set(service, value);
    }
}
