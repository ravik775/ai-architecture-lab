FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -B dependency:go-offline
COPY src ./src
RUN mvn -B -DskipTests package

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /build/target/otel-jaeger-demo-1.0.0.jar app.jar
EXPOSE 8091
ENTRYPOINT ["java", "-jar", "app.jar"]
