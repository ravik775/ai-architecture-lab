package org.ex.loanservice.config;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

/**
 * Pins the messaging topology declared by RabbitMqConfig. Previously
 * RabbitMQ was provisioned in docker-compose with no exchange, queue, or
 * binding ever declared in code (see RabbitMqConfigLogger, which only
 * logged connection settings) - these tests document and protect the
 * topology that now actually exists.
 */
class RabbitMqConfigTest {

    private final RabbitMqConfig config = new RabbitMqConfig();

    @Test
    void loanEventsExchange_isTopicExchangeWithExpectedName() {
        // Scenario: the exchange name is a public contract (routing keys
        // are published against it) - a rename here would silently break
        // both the publisher and any external consumer.
        TopicExchange exchange = config.loanEventsExchange();

        assertThat(exchange.getName()).isEqualTo("loan.events");
        assertThat(exchange.getType()).isEqualTo("topic");
    }

    @Test
    void loanSubmittedQueue_isDurableWithExpectedName() {
        // Scenario: durability matters - a non-durable queue would lose
        // pending LOAN_SUBMITTED notifications on a RabbitMQ restart.
        Queue queue = config.loanSubmittedQueue();

        assertThat(queue.getName()).isEqualTo("loan.submitted.queue");
        assertThat(queue.isDurable()).isTrue();
    }

    @Test
    void loanApprovedQueue_isDurableWithExpectedName() {
        Queue queue = config.loanApprovedQueue();

        assertThat(queue.getName()).isEqualTo("loan.approved.queue");
        assertThat(queue.isDurable()).isTrue();
    }

    @Test
    void loanSubmittedBinding_bindsQueueToExchangeWithSubmittedRoutingKey() {
        // Scenario: the binding is what actually routes a
        // convertAndSend(exchange, "loan.submitted", ...) call into the
        // submitted queue rather than the approved one (or nowhere).
        Queue queue = config.loanSubmittedQueue();
        TopicExchange exchange = config.loanEventsExchange();

        Binding binding = config.loanSubmittedBinding(queue, exchange);

        assertThat(binding.getExchange()).isEqualTo("loan.events");
        assertThat(binding.getRoutingKey()).isEqualTo("loan.submitted");
        assertThat(binding.getDestination()).isEqualTo("loan.submitted.queue");
    }

    @Test
    void loanApprovedBinding_bindsQueueToExchangeWithApprovedRoutingKey() {
        Queue queue = config.loanApprovedQueue();
        TopicExchange exchange = config.loanEventsExchange();

        Binding binding = config.loanApprovedBinding(queue, exchange);

        assertThat(binding.getExchange()).isEqualTo("loan.events");
        assertThat(binding.getRoutingKey()).isEqualTo("loan.approved");
        assertThat(binding.getDestination()).isEqualTo("loan.approved.queue");
    }

    @Test
    void rabbitTemplate_usesJsonMessageConverter_notJavaNativeSerialization() {
        // Scenario: Spring AMQP defaults to Java native serialization for
        // message bodies if no converter is configured, which is a
        // deserialization attack surface. This pins that the JSON
        // converter is actually wired onto the template, not just declared
        // as an unused bean.
        ConnectionFactory connectionFactory = mock(ConnectionFactory.class);
        Jackson2JsonMessageConverter jsonConverter = config.jsonMessageConverter();

        RabbitTemplate template = config.rabbitTemplate(connectionFactory, jsonConverter);

        assertThat(template.getMessageConverter()).isSameAs(jsonConverter);
    }
}
