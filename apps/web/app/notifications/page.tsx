import { Protected } from "@/components/protected";
import { NotificationsPage } from "../alerts/pages";

export default function NotificationsRoute() {
  return (
    <Protected>
      <NotificationsPage />
    </Protected>
  );
}
