FROM flink:1.18

# Python runtime for PyFlink + the feature-engine deps.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-dev build-essential wget \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

RUN rm -f /usr/lib/python3*/EXTERNALLY-MANAGED \
    && pip3 install --no-cache-dir "apache-flink==1.18.1" "redis>=5.0" "boto3>=1.34"

# Kafka connector (fat jar) onto the Flink classpath.
RUN wget -q -O /opt/flink/lib/flink-sql-connector-kafka-3.1.0-1.18.jar \
    https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.1.0-1.18/flink-sql-connector-kafka-3.1.0-1.18.jar

ENV PYTHONPATH=/jobs
