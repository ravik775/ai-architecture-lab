package org.ex.loanservice.config;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Declares the loan domain event topology. Previously RabbitMQ was
 * provisioned (see RabbitMqConfigLogger) with no exchange, queue, or
 * producer/consumer ever wired to it.
 */
@Configuration
public class RabbitMqConfig {

    public static final String LOAN_EVENTS_EXCHANGE = "loan.events";
    public static final String LOAN_SUBMITTED_QUEUE = "loan.submitted.queue";
    public static final String LOAN_APPROVED_QUEUE = "loan.approved.queue";
    public static final String LOAN_SUBMITTED_ROUTING_KEY = "loan.submitted";
    public static final String LOAN_APPROVED_ROUTING_KEY = "loan.approved";

    @Bean
    TopicExchange loanEventsExchange() {
        return new TopicExchange(LOAN_EVENTS_EXCHANGE);
    }

    @Bean
    Queue loanSubmittedQueue() {
        return QueueBuilder.durable(LOAN_SUBMITTED_QUEUE).build();
    }

    @Bean
    Queue loanApprovedQueue() {
        return QueueBuilder.durable(LOAN_APPROVED_QUEUE).build();
    }

    @Bean
    Binding loanSubmittedBinding(Queue loanSubmittedQueue, TopicExchange loanEventsExchange) {
        return BindingBuilder.bind(loanSubmittedQueue).to(loanEventsExchange).with(LOAN_SUBMITTED_ROUTING_KEY);
    }

    @Bean
    Binding loanApprovedBinding(Queue loanApprovedQueue, TopicExchange loanEventsExchange) {
        return BindingBuilder.bind(loanApprovedQueue).to(loanEventsExchange).with(LOAN_APPROVED_ROUTING_KEY);
    }

    /**
     * Spring AMQP defaults to Java native serialization for message bodies,
     * which is a deserialization attack surface. JSON keeps the wire format
     * both inspectable (see RabbitMQ management UI) and safe.
     */
    @Bean
    Jackson2JsonMessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory, Jackson2JsonMessageConverter jsonMessageConverter) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(jsonMessageConverter);
        return template;
    }
}
