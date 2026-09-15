import { Protected } from "@/components/protected";
import { RecordIrrigationPage } from "./pages";

export default async function RecordIrrigationRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Protected>
      <RecordIrrigationPage fieldId={id} />
    </Protected>
  );
}
