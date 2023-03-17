import openai
import argparse


openai.api_key = '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'


def get_response(msg):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=msg,
        temperature=0.3,
        max_tokens=1024,
        n=1
    )
    return response


def get_parser():
    parser = argparse.ArgumentParser(description='subtitle translator')
    parser.add_argument('-p', type=str, required=True, help='Prompt')
    return parser


if __name__ == '__main__':
    parser = get_parser()
    args = parser.parse_args()
    prompt = args.p

    system_msg = {'role': 'system',
                  'content': 'You are an assistant that speaks tranditional chinese.'}

    message = [system_msg, {'role': 'user', 'content': prompt}]
    response = get_response(message)
    print(response.choices[0].message.content)
