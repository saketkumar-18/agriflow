import { Protected } from "@/components/protected";
import { AccountPage } from "../alerts/pages";

export default function AccountRoute() {
  return (
    <Protected>
      <AccountPage />
    </Protected>
  );
}
