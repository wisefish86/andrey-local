import csv,json
from pathlib import Path

BASE=Path(__file__).parent
CSV_FILE=BASE/"songs.csv"
CFG_FILE=BASE/"replacements.json"
OUT_FILE=BASE/"songs.js"

def main():
    cfg=json.loads(CFG_FILE.read_text(encoding="utf-8"))
    songs={}
    rows=0
    unknown=set()
    replaced=0

    with open(CSV_FILE,encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f,delimiter=cfg["settings"]["csv_delimiter"])
        for r in reader:
            rows+=1
            artist=(r.get("Исполнитель") or "").replace("; ",", ").replace("; ",", ")
            title=(r.get("Название") or "").strip()
            key=(artist.lower(),title.lower())
            try:
                rating=int(r.get("Рейтинг") or 0)
            except:
                rating=0

            tags=[]
            raw=((r.get("Теги") or "")+";"+(r.get("Жанр") or "")).split(";")
            for t in raw:
                t=t.strip()
                if t in cfg["replace"]:
                    replaced+=1
                    val=cfg["replace"][t]
                    if not isinstance(val,list):
                        val=[val]
                    for x in val:
                        if x not in tags:
                            tags.append(x)
                elif t:
                    unknown.add(t)

            if key not in songs:
                songs[key]={"artist":artist,"title":title,"rating":rating,"tags":tags}
            else:
                songs[key]["rating"]=max(songs[key]["rating"],rating)
                songs[key]["tags"]=list(dict.fromkeys(songs[key]["tags"]+tags))

    result=list(songs.values())
    result.sort(key=lambda x:x["rating"],reverse=True)

    payload={
        "config":cfg,
        "songs":result
    }

    OUT_FILE.write_text(
        "window.REPERTOIRE="+json.dumps(payload,ensure_ascii=False,indent=2),
        encoding="utf-8"
    )

    print("Готово")
    print("Строк:",rows)
    print("Дублей удалено:",rows-len(result))
    print("Песен:",len(result))
    print("Замен тегов:",replaced)
    print("Неизвестных тегов:",len(unknown))
    if unknown:
        print("Неизвестные:",", ".join(sorted(unknown)))
    print("Создан songs.js")
    input("Enter")

if __name__=="__main__":
    main()
