import { Protected } from "@/components/protected";
import { AlertsPage } from "./pages";

export default function AlertsRoute() {
  return (
    <Protected>
      <AlertsPage />
    </Protected>
  );
}
