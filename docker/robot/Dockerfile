# The download stage is discarded; the final image contains only a JRE and ROBOT.
FROM alpine:3.21 AS download
ARG ROBOT_VERSION=1.9.11
# SHA-256 of robot.jar for ROBOT_VERSION; update together with the version.
ARG ROBOT_SHA256=53cd275c8e4c0dad1fc2c1c34174876795cd7d6b6926e1444adcbb0cb3c7ab26
RUN apk add --no-cache curl \
    && curl --fail --location --silent --show-error \
      --output /robot.jar \
      "https://github.com/ontodev/robot/releases/download/v${ROBOT_VERSION}/robot.jar" \
    && echo "${ROBOT_SHA256}  /robot.jar" | sha256sum -c -

FROM gcr.io/distroless/java21-debian12:nonroot
COPY --from=download /robot.jar /robot.jar
USER nonroot:nonroot
ENTRYPOINT ["java", "-jar", "/robot.jar"]
