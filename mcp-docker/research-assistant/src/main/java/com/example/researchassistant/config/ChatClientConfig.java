package com.example.researchassistant.config;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ChatClientConfig {

    @Bean
    ChatClient chatClient(ChatModel chatModel) {
        return ChatClient.builder(chatModel)
            .defaultSystem("""
                You are an internal research assistant. You have access to a `curl`
                tool that can fetch the contents of a URL. When a question needs
                current, factual, or post-training-cutoff information and the user's
                question implies or names a specific source, use curl to fetch it
                before answering instead of guessing. Keep answers concise and note
                when an answer is based on a fetched page rather than prior knowledge.
                """)
            .build();
    }
}
