package org.ex.loanservice;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * Smoke test: the full application context wires up.
 *
 * Runtime infrastructure is switched off rather than mocked, because none of it
 * is what this test is checking - it verifies bean wiring, not connectivity:
 *
 *  - reload-on-update registers a filesystem watcher over /spiffe-certs at
 *    startup and throws if the directory is absent. Those files only exist
 *    inside the container, where spiffe-helper writes them.
 *  - server.ssl needs a real SVID for the same reason.
 *  - eureka.instance.secure-port resolves ${LOAN_SERVER_PORT}, which is only
 *    set by docker-compose.
 *  - the RabbitMQ listener containers start eagerly and would dial a broker.
 *
 * Everything above is exercised for real by the live end-to-end flow; keeping
 * this test infra-free is what lets `mvn test` stay green off a laptop.
 */
@SpringBootTest(properties = {
        // Point the spiffe bundle at throwaway test certificates instead of
        // stubbing it out. The bundle is a real dependency of RestTemplateConfig,
        // so resolving it for real is what makes this smoke test meaningful -
        // it would catch a malformed bundle definition, which a disabled bundle
        // never would.
        "spring.ssl.bundle.pem.spiffe.keystore.certificate=classpath:test-certs/cert.pem",
        "spring.ssl.bundle.pem.spiffe.keystore.private-key=classpath:test-certs/key.pem",
        "spring.ssl.bundle.pem.spiffe.truststore.certificate=classpath:test-certs/cert.pem",
        // Watching a classpath resource is neither possible nor meaningful.
        "spring.ssl.bundle.pem.spiffe.reload-on-update=false",
        "server.ssl.enabled=false",
        "eureka.client.enabled=false",
        "spring.rabbitmq.listener.simple.auto-startup=false"
})
class LoanServiceApplicationTests {

    @Test
    void contextLoads() {
    }

}
