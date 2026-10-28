INSERT INTO log
    (severity,
    tag,
    message,
    timestamp,
    metadata)
VALUES
    (:severity,
     :tag,
     :message,
     :timestamp,
     :metadata);