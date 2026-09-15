import { Protected } from "@/components/protected";
import { HistoryPage } from "./pages";

export default function HistoryRoute() {
  return (
    <Protected>
      <HistoryPage />
    </Protected>
  );
}
