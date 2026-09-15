import { Protected } from "@/components/protected";
import { FarmDetailPage } from "../pages";

export default async function FarmRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Protected>
      <FarmDetailPage farmId={id} />
    </Protected>
  );
}
