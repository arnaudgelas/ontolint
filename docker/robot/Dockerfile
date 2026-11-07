# The download stage is discarded; the final image contains only a JRE and ROBOT.
FROM alpine:3.21 AS download
ARG ROBOT_VERSION=1.9.11
RUN apk add --no-cache curl \
    && curl --fail --location --silent --show-error \
      --output /robot.jar \
      "https://github.com/ontodev/robot/releases/download/v${ROBOT_VERSION}/robot.jar"

FROM gcr.io/distroless/java21-debian12:nonroot
COPY --from=download /robot.jar /robot.jar
USER nonroot:nonroot
ENTRYPOINT ["java", "-jar", "/robot.jar"]
