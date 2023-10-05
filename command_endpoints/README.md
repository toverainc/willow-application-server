# Willow Application Server Command Endpoints

With WAS mode enabled, Willow no longer communicates with command endpoints
directly. The message flow on wake is as follows:

1. Willow HTTP POST audio --> WIS
2. WIS responds JSON to Willow
3. Willow sends unmodified JSON from WIS to WAS
4. WAS forwards to configured endpoint
5. Endpoint responds to WAS
6. WAS responds JSON to Willow

The message format is fixed in steps 1,3,4,6.
The message format in steps 5 and 6 depends on the configured command endpoint.

Step 6 example message:

{
  "ok": true,
  "speech": "turned on light"
}
