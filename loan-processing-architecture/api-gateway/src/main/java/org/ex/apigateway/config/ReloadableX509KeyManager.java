package org.ex.apigateway.config;

import javax.net.ssl.SSLEngine;
import javax.net.ssl.X509ExtendedKeyManager;
import java.net.Socket;
import java.security.Principal;
import java.security.PrivateKey;
import java.security.cert.X509Certificate;

/**
 * X.509 key manager whose delegate can be swapped at runtime while the Netty
 * SslContext holding it stays the same object.
 *
 * JSSE consults the key manager on every handshake, so replacing the delegate
 * is enough for the next connection to present a freshly rotated SVID. That
 * matters because Netty's SslContext is immutable once built - without this
 * indirection the only way to pick up a rotated cert would be to rebuild the
 * SslContext and the HttpClient around it, i.e. restart the gateway.
 */
public final class ReloadableX509KeyManager extends X509ExtendedKeyManager {

    private volatile X509ExtendedKeyManager delegate;

    public void setDelegate(X509ExtendedKeyManager delegate) {
        this.delegate = delegate;
    }

    @Override
    public String[] getClientAliases(String keyType, Principal[] issuers) {
        return delegate.getClientAliases(keyType, issuers);
    }

    @Override
    public String chooseClientAlias(String[] keyType, Principal[] issuers, Socket socket) {
        return delegate.chooseClientAlias(keyType, issuers, socket);
    }

    /**
     * Reactor Netty is SSLEngine-based, so this - not chooseClientAlias - is
     * the method actually invoked for gateway -> loan-service calls.
     */
    @Override
    public String chooseEngineClientAlias(String[] keyType, Principal[] issuers, SSLEngine engine) {
        return delegate.chooseEngineClientAlias(keyType, issuers, engine);
    }

    @Override
    public String[] getServerAliases(String keyType, Principal[] issuers) {
        return delegate.getServerAliases(keyType, issuers);
    }

    @Override
    public String chooseServerAlias(String keyType, Principal[] issuers, Socket socket) {
        return delegate.chooseServerAlias(keyType, issuers, socket);
    }

    @Override
    public String chooseEngineServerAlias(String keyType, Principal[] issuers, SSLEngine engine) {
        return delegate.chooseEngineServerAlias(keyType, issuers, engine);
    }

    @Override
    public X509Certificate[] getCertificateChain(String alias) {
        return delegate.getCertificateChain(alias);
    }

    @Override
    public PrivateKey getPrivateKey(String alias) {
        return delegate.getPrivateKey(alias);
    }
}
