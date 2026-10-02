# RDS trust roots

`rds.pem` is the public AWS RDS global root certificate bundle fetched on
2026-10-02 from [AWS's trust store](https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem).
It is public certificate material, not credentials. The deployment image copies
these reviewed bytes rather than downloading certificates at startup.

Review AWS certificate rotation guidance and refresh this file deliberately before
certificate expiry or regional CA changes; rebuild and redeploy the immutable image.
The database client requires `sslmode=verify-full` and uses the actual RDS hostname.
