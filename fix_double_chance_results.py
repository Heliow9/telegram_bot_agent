from app.db import SessionLocal
from app.models import Prediction


DRY_RUN = False


def normalize(value):
    return str(value or "").strip().upper()


def is_winner(pick: str, result: str) -> bool:
    pick = normalize(pick)
    result = normalize(result)

    if not pick or not result:
        return False

    if pick in {"1", "X", "2"}:
        return pick == result

    if pick == "1X":
        return result in {"1", "X"}

    if pick == "X2":
        return result in {"X", "2"}

    if pick == "12":
        return result in {"1", "2"}

    return False


def main():
    db = SessionLocal()

    try:
        rows = (
            db.query(Prediction)
            .filter(Prediction.market_type == "double_chance")
            .all()
        )

        print(f"[FIX] Registros double chance encontrados: {len(rows)}")
        print(f"[FIX] DRY_RUN={DRY_RUN}")
        print()

        updated_pick_count = 0
        updated_status_count = 0
        skipped_count = 0

        for item in rows:
            current_pick = normalize(item.pick)
            correct_pick = normalize(item.double_chance_pick)
            result = normalize(item.result)
            current_status = str(item.status or "").strip().lower()

            if not correct_pick:
                print(
                    f"[SKIP] fixture_id={item.fixture_id} | "
                    f"sem double_chance_pick | pick_atual={current_pick}"
                )
                skipped_count += 1
                continue

            changed = False

            print(
                f"[CHECK] fixture_id={item.fixture_id} | "
                f"{item.home_team} x {item.away_team} | "
                f"pick_atual={current_pick} | pick_correto={correct_pick} | "
                f"status={current_status} | result={result}"
            )

            if current_pick != correct_pick:
                print(
                    f"  -> corrigindo pick: {current_pick} => {correct_pick}"
                )
                if not DRY_RUN:
                    item.pick = correct_pick
                updated_pick_count += 1
                changed = True

            if result and current_status in {"hit", "miss"}:
                new_status = "hit" if is_winner(correct_pick, result) else "miss"

                if new_status != current_status:
                    print(
                        f"  -> corrigindo status: {current_status} => {new_status}"
                    )
                    if not DRY_RUN:
                        item.status = new_status
                    updated_status_count += 1
                    changed = True

            if not changed:
                print("  -> sem alterações")

            print()

        if DRY_RUN:
            db.rollback()
            print("[FIX] DRY RUN concluído. Nenhuma alteração foi salva.")
        else:
            db.commit()
            print("[FIX] Alterações salvas com sucesso.")

        print()
        print(f"[FIX] Picks corrigidos: {updated_pick_count}")
        print(f"[FIX] Status corrigidos: {updated_status_count}")
        print(f"[FIX] Ignorados: {skipped_count}")

    except Exception as e:
        db.rollback()
        print(f"[FIX] Erro: {e}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()