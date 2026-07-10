const form = document.querySelector("#upload-form");
const result = document.querySelector("#upload-result");
const taskStatus = document.querySelector("#task-status");
const errors = document.querySelector("#upload-errors");
const warnings = document.querySelector("#upload-warnings");
const createTask = document.querySelector("#create-task");

let currentUploadId = null;

function renderDiagnostics(target, diagnostics) {
  target.replaceChildren();
  diagnostics.forEach((diagnostic) => {
    const item = document.createElement("li");
    item.textContent = [
      diagnostic.filename,
      diagnostic.line ? `第 ${diagnostic.line} 行` : "",
      diagnostic.field,
      diagnostic.reason,
    ].filter(Boolean).join(" · ");
    target.append(item);
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  currentUploadId = null;
  createTask.disabled = true;
  result.textContent = "正在校验…";
  taskStatus.textContent = "";
  errors.replaceChildren();
  warnings.replaceChildren();

  try {
    const response = await fetch("/api/uploads", {
      method: "POST",
      body: new FormData(form),
    });
    const payload = await response.json();
    renderDiagnostics(warnings, payload.warnings || []);
    if (payload.status === "valid") {
      currentUploadId = payload.upload_id;
      result.textContent = `校验通过：${payload.valid_records} 条有效记录`;
      createTask.disabled = false;
      return;
    }
    result.textContent = "校验未通过";
    renderDiagnostics(errors, payload.errors || [{
      filename: "",
      line: 0,
      field: "",
      reason: payload.message || "上传失败",
    }]);
  } catch {
    result.textContent = "上传失败，请确认本地服务正在运行后重试。";
  }
});

createTask.addEventListener("click", async () => {
  if (!currentUploadId) {
    return;
  }
  createTask.disabled = true;
  taskStatus.textContent = "正在创建任务…";
  try {
    const response = await fetch("/api/tasks", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({upload_id: currentUploadId, runner_mode: "fixture"}),
    });
    const payload = await response.json();
    if (!response.ok) {
      taskStatus.textContent = payload.message || "创建任务失败";
      createTask.disabled = false;
      return;
    }
    const link = document.createElement("a");
    link.href = `/tasks/${payload.task_id}`;
    link.textContent = `任务 ${payload.task_id} 已创建，点击查看`;
    taskStatus.replaceChildren(link);
  } catch {
    taskStatus.textContent = "创建任务失败，请确认本地服务正在运行后重试。";
    createTask.disabled = false;
  }
});
