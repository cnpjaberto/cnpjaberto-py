"""SDK usage examples.

Set CNPJABERTO_API_KEY in your environment for the Pro daily quota:

    export CNPJABERTO_API_KEY=your_key_here
"""
from cnpjaberto import Client


def main() -> None:
    with Client() as cnpj:
        nubank = cnpj.lookup("18236120000158")
        matriz = nubank["estabelecimentos"][0]
        print(f"{nubank['razao_social']} — {matriz['situacao_cadastral']}")

        results = cnpj.search("padaria", per_page=5)
        for hit in results["results"]:
            print(f"  {hit['cnpj']}  {hit['razao_social']}")

        snap = cnpj.panorama_year(2024)
        print(f"\n2024: {snap['abertas']:,} opened · {snap['fechadas']:,} closed")


if __name__ == "__main__":
    main()
