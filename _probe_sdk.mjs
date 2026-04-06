// probe_sdk.mjs - run with: node probe_sdk.mjs
import sdk from "C:\\Users\\Asherre Roamin\\.lmstudio\\extensions\\plugins\\roamin\\roamin-python-tools\\node_modules\\@lmstudio\\sdk\\dist\\index.mjs";

const toolKeys = Object.keys(sdk).filter(k => k.toLowerCase().includes("tool"));
console.log("Tool-related exports:", toolKeys.join(", "));

const { rawFunctionTool } = sdk;
if (rawFunctionTool) {
  console.log("\nrawFunctionTool found. Source (first 600 chars):");
  console.log(rawFunctionTool.toString().slice(0, 600));
} else {
  console.log("rawFunctionTool not a named export, checking default...");
  console.log("All keys:", Object.keys(sdk).slice(0, 30).join(", "));
}
