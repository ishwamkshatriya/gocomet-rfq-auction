import React from "react";
import { STATUS_LABEL } from "../format.js";

export default function StatusBadge({ status }) {
  return <span className={`badge ${status.toLowerCase()}`}>{STATUS_LABEL[status] || status}</span>;
}
