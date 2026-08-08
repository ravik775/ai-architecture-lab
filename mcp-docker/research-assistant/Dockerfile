# --- Build stage ---
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build

# Cache dependency resolution separately from source changes
COPY pom.xml .
RUN mvn -B dependency:go-offline

COPY src ./src
RUN mvn -B -DskipTests package

# --- Runtime stage ---
FROM eclipse-temurin:21-jre-alpine
RUN addgroup -S app && adduser -S app -G app
WORKDIR /app
COPY --from=build /build/target/research-assistant-*.jar app.jar
USER app
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
