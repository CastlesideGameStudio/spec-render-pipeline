Below is a **concise “cheat sheet”** of the RunPod **v1 REST** API based on the documentation you provided. It focuses on the main endpoints for Pods, Serverless Endpoints, Network Volumes, Templates, and Billing. Use this for quick reference—always check the official docs at <https://rest.runpod.io/v1/docs> for complete details, request/response schemas, and any updates.

---

## Base URL & Authentication

- **Base URL**: `https://rest.runpod.io/v1`
- **Authentication**:  
  - Use a **Bearer** token in the `Authorization` header.  
  - Example:  
    ```http
    Authorization: Bearer YOUR_SECRET_TOKEN
    Content-Type: application/json
    ```

---

## Pods

| **Endpoint**                        | **Method** | **Description**                                         |
|------------------------------------|-----------|---------------------------------------------------------|
| **/pods**                          | `POST`    | Create a new Pod (On-Demand or Community).             |
|                                    | `GET`     | List all Pods in your account.                         |
| **/pods/{podId}**                  | `GET`     | Get details of one Pod (status, GPU type, etc.).       |
|                                    | `PATCH`   | Update certain Pod fields (e.g., name, env).           |
|                                    | `DELETE`  | Delete a Pod.                                          |
| **/pods/{podId}/update**           | `POST`    | Apply changes (like a “redeploy” or environment vars). |
| **/pods/{podId}/start**            | `POST`    | Start a previously stopped Pod.                        |
| **/pods/{podId}/stop**             | `POST`    | Stop (pause) a running Pod.                            |
| **/pods/{podId}/reset**            | `POST`    | Reset (often means a full container restart).          |
| **/pods/{podId}/restart**          | `POST`    | Graceful restart of the Pod.                           |
| **/pods/{podId}/logs**             | `GET`     | Fetch Pod console logs (if available).                 |

### Example: Create a Pod (On-Demand)

```http
POST /v1/pods
Authorization: Bearer YOUR_SECRET_TOKEN
Content-Type: application/json

{
  "name": "my-pod",
  "cloud_type": "SECURE",          // "COMMUNITY" for spot
  "gpuTypeId": "NVIDIA A40",
  "gpuCount": 1,
  "volumeInGb": 20,
  "containerDiskInGb": 20,
  "imageName": "ghcr.io/org/repo:latest",
  "env": {
    "MYVAR": "somevalue"
  }
}
```

---

## Serverless Endpoints

| **Endpoint**                                | **Method** | **Description**                                         |
|--------------------------------------------|-----------|---------------------------------------------------------|
| **/endpoints**                             | `POST`    | Create a serverless Endpoint (like a Worker).          |
|                                            | `GET`     | List all your Endpoints.                               |
| **/endpoints/{endpointId}**               | `GET`     | Get details of an Endpoint (GPU, name, etc.).          |
|                                            | `PATCH`   | Update Endpoint fields (e.g., env, concurrency).       |
|                                            | `DELETE`  | Delete an Endpoint.                                    |
| **/endpoints/{endpointId}/update**         | `POST`    | Apply changes or redeploy the Endpoint.                |

### Example: Create a Serverless Endpoint

```http
POST /v1/endpoints
Authorization: Bearer YOUR_SECRET_TOKEN
Content-Type: application/json

{
  "name": "my-serverless-endpoint",
  "gpuIds": "NVIDIA A100 80GB PCIe", // or blank for CPU
  "workersMin": 0,
  "workersMax": 1,
  "imageName": "myorg/myimage:serverless",
  "env": {
    "FOO": "bar"
  }
}
```

---

## Network Volumes

| **Endpoint**                                       | **Method** | **Description**                       |
|---------------------------------------------------|-----------|---------------------------------------|
| **/networkvolumes**                               | `POST`    | Create a new Network Volume.          |
|                                                   | `GET`     | List your Network Volumes.            |
| **/networkvolumes/{networkVolumeId}**             | `GET`     | Get details for one Network Volume.   |
|                                                   | `PATCH`   | Update the Volume (size, name, etc.). |
|                                                   | `DELETE`  | Delete (deallocate) a Volume.         |
| **/networkvolumes/{networkVolumeId}/update**      | `POST`    | Redeploy or reconfigure the Volume.   |

---

## Templates

| **Endpoint**                             | **Method** | **Description**                                                 |
|-----------------------------------------|-----------|-----------------------------------------------------------------|
| **/templates**                          | `POST`    | Create a template (Pod or Serverless).                          |
|                                         | `GET`     | List templates in your account.                                 |
| **/templates/{templateId}**            | `GET`     | Show details of a single template.                              |
|                                         | `PATCH`   | Update the template (e.g., new container image).                |
|                                         | `DELETE`  | Remove the template entirely.                                   |
| **/templates/{templateId}/update**     | `POST`    | Redeploy / apply changes to an existing template.               |

---

## Container Registry Auth

| **Endpoint**                                           | **Method** | **Description**                                 |
|-------------------------------------------------------|-----------|-------------------------------------------------|
| **/containerregistryauth**                            | `POST`    | Add credentials for private Docker registries.  |
|                                                       | `GET`     | List your container registry auth entries.      |
| **/containerregistryauth/{containerRegistryAuthId}**  | `GET`     | Show a single container registry auth record.   |
|                                                       | `DELETE`  | Delete an auth record.                          |

---

## Billing

| **Endpoint**       | **Method** | **Description**                                                   |
|--------------------|-----------|-------------------------------------------------------------------|
| **/billing/pods**          | `GET`     | Retrieve cost usage for your Pods over time.                     |
| **/billing/endpoints**     | `GET`     | Retrieve cost usage for your Serverless endpoints over time.     |
| **/billing/networkvolumes**| `GET`     | Retrieve cost usage for your Network Volumes.                    |

### Example: Bill usage for Pods

```http
GET /v1/billing/pods?startTime=2023-09-01T00:00:00Z&endTime=2023-09-30T23:59:59Z&bucketSize=day
Authorization: Bearer YOUR_SECRET_TOKEN
```

**Query Params**:
- `startTime` / `endTime` – ISO8601 date/time range
- `bucketSize` in { `hour`, `day`, `week`, `month`, `year` }
- `gpuTypeId` – filter by GPU type
- `podId` – filter to a specific Pod
- `grouping` – how to group the billing records (`podId`, `gpuTypeId`)

Response typically returns an array of usage records:
```json
[
  {
    "amount": 100.5,
    "diskSpaceBilledGb": 50,
    "endpointId": "string",
    "gpuTypeId": "string",
    "podId": "string",
    "time": "2023-01-01T00:00:00Z",
    "timeBilledMs": 3600000
  }
]
```

---

## Error Handling

- **HTTP 4xx**: Usually a malformed request or a missing resource.  
- **HTTP 5xx**: Internal server error or capacity issues.  
- The response often includes a JSON structure with `"error"` or `"message"` explaining the failure.

---

## Minimal Example Flow (Pods)

1. **List existing Pods**  
   ```http
   GET /v1/pods
   Authorization: Bearer YOUR_SECRET_TOKEN
   ```
2. **Create a Pod**  
   ```http
   POST /v1/pods
   { ...payload... }
   ```
3. **Poll Pod status**  
   ```http
   GET /v1/pods/{podId}
   ```
   until `status` != `"Running"`.
4. **Delete the Pod** (optional)  
   ```http
   DELETE /v1/pods/{podId}
   ```

---

### Final Notes

- **All endpoints** listed above require the `Authorization: Bearer <TOKEN>`.
- **Check capacity** (especially for GPUs) if you run into errors about availability.
- **Official docs**: <https://rest.runpod.io/v1/docs> or `GET /v1/openapi.json`.

That’s the concise rundown of the **v1 REST** endpoints for RunPod.