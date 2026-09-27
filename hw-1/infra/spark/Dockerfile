FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless curl procps \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/lib/jvm/java-17-openjdk-* /usr/lib/jvm/java-17

ENV JAVA_HOME=/usr/lib/jvm/java-17

RUN pip install --no-cache-dir "pyspark==3.5.9" "boto3"

RUN SPARK_JARS="$(python3 -c 'import os, pyspark; print(os.path.join(os.path.dirname(pyspark.__file__), "jars"))')" \
    && curl -fsSL -o "$SPARK_JARS/iceberg-spark-runtime-3.5_2.12-1.11.0.jar" \
       https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.11.0/iceberg-spark-runtime-3.5_2.12-1.11.0.jar \
    && curl -fsSL -o "$SPARK_JARS/hadoop-aws-3.3.4.jar" \
       https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar \
    && curl -fsSL -o "$SPARK_JARS/aws-java-sdk-bundle-1.12.262.jar" \
       https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar \
    && curl -fsSL -o "$SPARK_JARS/postgresql-42.7.3.jar" \
       https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.3/postgresql-42.7.3.jar \
    && curl -fsSL -o "$SPARK_JARS/iceberg-aws-bundle-1.11.0.jar" \
       https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-aws-bundle/1.11.0/iceberg-aws-bundle-1.11.0.jar

WORKDIR /opt/spark/work-dir

CMD ["sleep", "infinity"]
