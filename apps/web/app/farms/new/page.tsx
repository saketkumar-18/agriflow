import { Protected } from "@/components/protected";
import { NewFarmPage } from "../pages";

export default function NewFarmRoute() {
  return (
    <Protected>
      <NewFarmPage />
    </Protected>
  );
}
