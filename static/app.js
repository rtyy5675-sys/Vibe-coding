const form = document.querySelector("#upload-form");
const result = document.querySelector("#upload-result");
const errors = document.querySelector("#upload-errors");
const warnings = document.querySelector("#upload-warnings");
const createTask = document.querySelector("#create-task");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  createTask.disabled = true;
  result.textContent = "正在校验…";
  errors.replaceChildren();
  warnings.replaceChildren();

  try {
    const response = await fetch("/api/uploads", {
      method: "POST",
      body: new FormData(form),
    });
    const payload = await response.json();
    (payload.warnings || []).forEach((warning) => {
      const item = document.createElement("li");
      item.textContent = [
        warning.filename,
        warning.line ? `第 ${warning.line} 行` : "",
        warning.field,
        warning.reason,
      ].filter(Boolean).join(" · ");
      warnings.append(item);
    });
    if (payload.status === "valid") {
      result.textContent = `校验通过：${payload.valid_records} 条有效记录`;
      createTask.disabled = false;
      return;
    }
    result.textContent = "校验未通过";
    const diagnostics = payload.errors || [{
      filename: "",
      line: 0,
      field: "",
      reason: payload.reason || "上传失败",
    }];
    diagnostics.forEach((diagnostic) => {
      const item = document.createElement("li");
      item.textContent = [
        diagnostic.filename,
        diagnostic.line ? `第 ${diagnostic.line} 行` : "",
        diagnostic.field,
        diagnostic.reason,
      ].filter(Boolean).join(" · ");
      errors.append(item);
    });
  } catch {
    result.textContent = "上传失败，请确认本地服务正在运行后重试。";
  }
});
