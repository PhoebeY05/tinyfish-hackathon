const uploadBtn = document.getElementById("uploadBtn");
const fileInput = document.getElementById("photosZip");
const geographyInput = document.getElementById("geography");
const statusNode = document.getElementById("status");
const resultsNode = document.getElementById("results");
const downloadNode = document.getElementById("download");

function setStatus(text) {
  statusNode.textContent = text;
}

function renderResults(payload) {
  resultsNode.innerHTML = "";

  for (const image of payload.images || []) {
    const card = document.createElement("article");
    card.className = "card";

    const altText = (image.alternate_candidates || [])
      .map((item) => `${item.common_name} (${item.confidence})`)
      .join(", ");

    const badge = image.confidence_dispute?.status || "no_dispute";

    card.innerHTML = `
      <h3>${image.primary_prediction.common_name}</h3>
      <p class="meta"><strong>${image.primary_prediction.scientific_name}</strong></p>
      <p class="meta">Confidence: ${image.primary_prediction.confidence}</p>
      <p class="meta">Alternates: ${altText || "-"}</p>
      <p>${image.location_context.last_spotted_text} (${image.location_context.source})</p>
      <p><span class="badge ${badge}">${badge}</span></p>
      <p class="meta">${image.confidence_dispute.reason}</p>
    `;

    resultsNode.appendChild(card);
  }
}

async function pollJob(jobId) {
  while (true) {
    const res = await fetch(`/jobs/${jobId}`);
    if (!res.ok) {
      throw new Error("Unable to fetch job status");
    }

    const status = await res.json();
    setStatus(
      `Status: ${status.status} | Step: ${status.progress.current_step} | ${status.progress.processed_images}/${status.progress.total_images}`
    );

    if (status.status === "completed") {
      return;
    }

    if (status.status === "failed") {
      throw new Error(status.error || "Job failed");
    }

    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
}

async function runUpload() {
  const file = fileInput.files?.[0];
  if (!file) {
    setStatus("Choose a .zip file first.");
    return;
  }

  uploadBtn.disabled = true;
  downloadNode.innerHTML = "";
  resultsNode.innerHTML = "";

  try {
    const formData = new FormData();
    formData.append("photosZip", file);
    formData.append("geography", geographyInput.value || "Singapore");

    setStatus("Uploading zip...");

    const uploadRes = await fetch("/uploads", {
      method: "POST",
      body: formData
    });

    if (!uploadRes.ok) {
      const errorText = await uploadRes.text();
      throw new Error(errorText || "Upload failed");
    }

    const uploadData = await uploadRes.json();
    await pollJob(uploadData.jobId);

    setStatus("Job complete. Fetching results...");

    const resultsRes = await fetch(`/jobs/${uploadData.jobId}/results`);
    if (!resultsRes.ok) {
      throw new Error("Failed to fetch final results");
    }

    const report = await resultsRes.json();
    renderResults(report);

    downloadNode.innerHTML = `<a href="/jobs/${uploadData.jobId}/download">Download bird-report.zip</a>`;
    setStatus("Done. Results rendered below.");
  } catch (err) {
    setStatus(`Error: ${err.message}`);
  } finally {
    uploadBtn.disabled = false;
  }
}

uploadBtn.addEventListener("click", runUpload);
