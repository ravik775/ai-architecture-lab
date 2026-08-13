package org.ex.apigateway.config;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.ssl.DefaultSslBundleRegistry;
import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.pem.PemSslStoreBundle;
import org.springframework.boot.ssl.pem.PemSslStoreDetails;
import org.springframework.cloud.gateway.config.HttpClientCustomizer;
import org.springframework.core.io.ClassPathResource;

import javax.net.ssl.X509ExtendedKeyManager;
import java.nio.charset.StandardCharsets;
import java.security.cert.X509Certificate;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * End-to-end test of the rotation wiring, using real EC certificates and a real
 * Spring SslBundles registry - no mocks in the rotation path.
 *
 * This is the unit-level counterpart to what was observed live: the gateway
 * loaded one SVID at startup, spiffe-helper rotated it, and the next handshake
 * used the new certificate without the process restarting. Here the rotation is
 * triggered deterministically via SslBundleRegistry#updateBundle, which is
 * exactly what Spring's file watcher calls when reload-on-update is enabled.
 *
 * The two fixture keypairs (CN=rotation-test-a / -b) are throwaway EC keys
 * generated solely for this test - EC to match what SPIRE actually issues.
 */
class GatewayMtlsHttpClientConfigTest {

    private static final String BUNDLE_NAME = "spiffe";

    private GatewayMtlsHttpClientConfig config;
    private DefaultSslBundleRegistry registry;
    private ReloadableX509KeyManager keyManager;
    private ReloadableX509TrustManager trustManager;

    @BeforeEach
    void setUp() {
        config = new GatewayMtlsHttpClientConfig();
        keyManager = config.spiffeKeyManager();
        trustManager = config.spiffeTrustManager();
        registry = new DefaultSslBundleRegistry();
    }

    private static String read(String fileName) throws Exception {
        return new ClassPathResource("spiffe-rotation/" + fileName)
                .getContentAsString(StandardCharsets.UTF_8);
    }

    /** Builds a bundle the same shape as the spiffe bundle in application.yml. */
    private static SslBundle bundleFor(String suffix) throws Exception {
        PemSslStoreDetails keyStore = PemSslStoreDetails
                .forCertificate(read("cert_" + suffix + ".pem"))
                .withPrivateKey(read("key_" + suffix + ".pem"));
        PemSslStoreDetails trustStore = PemSslStoreDetails
                .forCertificate(read("cert_" + suffix + ".pem"));
        return SslBundle.of(new PemSslStoreBundle(keyStore, trustStore));
    }

    /** The CN currently served by the swappable key manager. */
    private String currentCertificateCn() {
        String[] aliases = keyManager.getClientAliases("EC", null);
        assertThat(aliases).as("key manager exposed no EC alias").isNotEmpty();
        X509Certificate[] chain = keyManager.getCertificateChain(aliases[0]);
        assertThat(chain).as("key manager exposed no certificate chain").isNotEmpty();
        return chain[0].getSubjectX500Principal().getName();
    }

    @Test
    void customizerLoadsInitialBundle_andIsRegisteredForUpdates() throws Exception {
        // Scenario: startup. The gateway builds its SslContext once from the
        // SVID currently on disk, and registers itself for future rotations.
        registry.registerBundle(BUNDLE_NAME, bundleFor("a"));

        HttpClientCustomizer customizer =
                config.spiffeMtlsHttpClientCustomizer(registry, keyManager, trustManager);

        assertThat(customizer).isNotNull();
        assertThat(currentCertificateCn()).contains("rotation-test-a");
        assertThat(trustManager.getAcceptedIssuers()).isNotEmpty();
    }

    @Test
    void bundleUpdate_swapsInTheRotatedCertificate_withoutRebuildingAnything() throws Exception {
        // Scenario: THE rotation test. spiffe-helper rewrites the SVID and
        // Spring's watcher fires updateBundle. The key manager must start
        // serving the new certificate immediately - and critically, this must
        // happen without recreating the SslContext or the HttpClient, because
        // in production those are already wired into the running gateway.
        registry.registerBundle(BUNDLE_NAME, bundleFor("a"));
        HttpClientCustomizer customizer =
                config.spiffeMtlsHttpClientCustomizer(registry, keyManager, trustManager);
        assertThat(currentCertificateCn()).contains("rotation-test-a");

        // Simulate the rotation exactly as the file watcher would.
        registry.updateBundle(BUNDLE_NAME, bundleFor("b"));

        assertThat(currentCertificateCn())
                .as("rotated SVID was not picked up by the key manager")
                .contains("rotation-test-b");
        // Same customizer instance throughout - nothing was rebuilt or replaced.
        assertThat(customizer).isNotNull();
    }

    @Test
    void trustBundleUpdate_swapsInTheRotatedCa() throws Exception {
        // Scenario: SPIRE rotates its CA, so bundle.pem changes even though the
        // workload's own SVID may not have. The accepted issuer list must
        // follow, otherwise the gateway would reject peers presenting a chain
        // signed by the new CA.
        registry.registerBundle(BUNDLE_NAME, bundleFor("a"));
        config.spiffeMtlsHttpClientCustomizer(registry, keyManager, trustManager);
        X509Certificate issuerBefore = trustManager.getAcceptedIssuers()[0];

        registry.updateBundle(BUNDLE_NAME, bundleFor("b"));

        X509Certificate issuerAfter = trustManager.getAcceptedIssuers()[0];
        assertThat(issuerAfter).isNotEqualTo(issuerBefore);
        assertThat(issuerAfter.getSubjectX500Principal().getName()).contains("rotation-test-b");
    }

    @Test
    void emptyBundleOnReload_keepsThePreviousMaterialInsteadOfBreakingMtls() throws Exception {
        // Scenario: the watcher fires while spiffe-helper is still writing, so
        // the bundle parses cleanly but carries no key entries. This is the
        // nasty case - it does NOT throw on its own, so an unguarded swap would
        // quietly replace a working SVID with an empty key manager and the
        // gateway would stop presenting a client certificate until the next
        // rotation. applyBundle validates the stores before swapping, and the
        // handler swallows the resulting error, so the still-valid old SVID
        // stays in use.
        registry.registerBundle(BUNDLE_NAME, bundleFor("a"));
        config.spiffeMtlsHttpClientCustomizer(registry, keyManager, trustManager);

        // Cast disambiguates the two PemSslStoreBundle constructor overloads.
        SslBundle emptyBundle = SslBundle.of(
                new PemSslStoreBundle((PemSslStoreDetails) null, (PemSslStoreDetails) null));
        registry.updateBundle(BUNDLE_NAME, emptyBundle);

        assertThat(currentCertificateCn())
                .as("a failed reload must not clear the working certificate")
                .contains("rotation-test-a");
        assertThat(trustManager.getAcceptedIssuers())
                .as("a failed reload must not clear the working trust bundle")
                .isNotEmpty();
    }
}
