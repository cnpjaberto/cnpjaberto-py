"""Exemplos de uso do SDK.

Defina CNPJABERTO_API_KEY no ambiente para usar a cota diária do plano Pro:

    export CNPJABERTO_API_KEY=sua_chave_aqui
"""
from cnpjaberto import Client


def main() -> None:
    with Client() as cnpj:
        nubank = cnpj.lookup("18236120000158")
        matriz = nubank["estabelecimentos"][0]
        print(f"{nubank['razao_social']}, {matriz['situacao_cadastral']}")

        results = cnpj.search("padaria", per_page=5)
        for hit in results["results"]:
            print(f"  {hit['cnpj']}  {hit['razao_social']}")

        snap = cnpj.panorama_year(2024)
        print(f"\n2024: {snap['abertas']:,} abertas, {snap['fechadas']:,} fechadas")


if __name__ == "__main__":
    main()
