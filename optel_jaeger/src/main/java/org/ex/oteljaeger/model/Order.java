package org.ex.oteljaeger.model;

public record Order(String id, String sku, int quantity, String status) {
}
