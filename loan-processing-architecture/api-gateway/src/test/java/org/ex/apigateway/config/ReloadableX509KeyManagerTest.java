package org.ex.apigateway.config;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import javax.net.ssl.SSLEngine;
import javax.net.ssl.X509ExtendedKeyManager;
import java.net.Socket;
import java.security.PrivateKey;
import java.security.cert.X509Certificate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * The swappable key manager is the mechanism that makes SVID rotation possible
 * without a restart: Netty's SslContext is immutable once built, so the only
 * way a rotated certificate reaches the wire is if the key manager it holds
 * starts answering with the new material.
 *
 * These tests pin that contract - every call must go to the *current* delegate,
 * and swapping the delegate must take effect immediately.
 */
class ReloadableX509KeyManagerTest {

    private X509ExtendedKeyManager oldDelegate;
    private X509ExtendedKeyManager newDelegate;
    private ReloadableX509KeyManager keyManager;
    // Real mock instances rather than nulls: Mockito's any(Type.class) matchers
    // deliberately do not match null, and a live SSLEngine/Socket is closer to
    // what the JSSE handshake actually passes in.
    private SSLEngine engine;
    private Socket socket;

    @BeforeEach
    void setUp() {
        oldDelegate = mock(X509ExtendedKeyManager.class);
        newDelegate = mock(X509ExtendedKeyManager.class);
        keyManager = new ReloadableX509KeyManager();
        keyManager.setDelegate(oldDelegate);
        engine = mock(SSLEngine.class);
        socket = mock(Socket.class);
    }

    @Test
    void chooseEngineClientAlias_isDelegated() {
        // Scenario: this is THE method that matters in production. Reactor
        // Netty is SSLEngine-based, so gateway -> loan-service handshakes call
        // chooseEngineClientAlias, not chooseClientAlias. If this override were
        // dropped, X509ExtendedKeyManager's default implementation would return
        // null, the gateway would present no client certificate, and mTLS would
        // fail with a confusing handshake error rather than a compile error.
        when(oldDelegate.chooseEngineClientAlias(any(), any(), any())).thenReturn("spiffe-alias");

        String alias = keyManager.chooseEngineClientAlias(new String[] { "EC" }, null, engine);

        assertThat(alias).isEqualTo("spiffe-alias");
        verify(oldDelegate).chooseEngineClientAlias(any(), any(), any());
    }

    @Test
    void swappingDelegate_redirectsSubsequentCallsToTheNewDelegate() {
        // Scenario: the rotation itself. Before the swap the manager must
        // answer from the old SVID; immediately after, from the new one - with
        // no further calls landing on the old delegate. This is exactly what
        // the bundle update handler relies on.
        when(oldDelegate.chooseEngineClientAlias(any(), any(), any())).thenReturn("old-svid");
        when(newDelegate.chooseEngineClientAlias(any(), any(), any())).thenReturn("new-svid");

        assertThat(keyManager.chooseEngineClientAlias(new String[] { "EC" }, null, engine))
                .isEqualTo("old-svid");

        keyManager.setDelegate(newDelegate);

        assertThat(keyManager.chooseEngineClientAlias(new String[] { "EC" }, null, engine))
                .isEqualTo("new-svid");
        // the old delegate must not be consulted again after rotation
        verify(oldDelegate).chooseEngineClientAlias(any(), any(), any());
    }

    @Test
    void certificateChainAndPrivateKey_comeFromTheCurrentDelegate() {
        // Scenario: after rotation the chain and the matching private key must
        // come from the SAME (new) delegate. Serving a new chain with the old
        // key - or vice versa - produces a handshake failure that is painful to
        // diagnose, so both are asserted against the post-swap delegate.
        X509Certificate[] newChain = new X509Certificate[] { mock(X509Certificate.class) };
        PrivateKey newKey = mock(PrivateKey.class);
        when(newDelegate.getCertificateChain("a")).thenReturn(newChain);
        when(newDelegate.getPrivateKey("a")).thenReturn(newKey);

        keyManager.setDelegate(newDelegate);

        assertThat(keyManager.getCertificateChain("a")).isSameAs(newChain);
        assertThat(keyManager.getPrivateKey("a")).isSameAs(newKey);
        verify(oldDelegate, never()).getCertificateChain(any());
        verify(oldDelegate, never()).getPrivateKey(any());
    }

    @Test
    void remainingKeyManagerMethods_areDelegated() {
        // Scenario: the non-engine overloads are unused by reactor-netty today
        // but are part of the X509ExtendedKeyManager contract - a partially
        // delegating manager would silently misbehave if the transport ever
        // changed. Cheap to pin, so pinned.
        keyManager.getClientAliases("EC", null);
        keyManager.chooseClientAlias(new String[] { "EC" }, null, socket);
        keyManager.getServerAliases("EC", null);
        keyManager.chooseServerAlias("EC", null, socket);

        verify(oldDelegate).getClientAliases("EC", null);
        verify(oldDelegate).chooseClientAlias(any(), any(), any(Socket.class));
        verify(oldDelegate).getServerAliases("EC", null);
        verify(oldDelegate).chooseServerAlias(any(), any(), any(Socket.class));
    }
}
