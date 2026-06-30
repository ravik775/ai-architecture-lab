FROM maven:3.9.11-eclipse-temurin-21 AS builder

ARG SERVICE_NAME

WORKDIR /app

COPY . .

RUN mvn clean package -DskipTests

FROM eclipse-temurin:21-jre

ARG SERVICE_NAME

COPY --from=builder \
    /app/${SERVICE_NAME}/target/*.jar \
    app.jar

ENTRYPOINT ["java","-jar","/app.jar"]