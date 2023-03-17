import openai
import time
import argparse


def get_response(msg):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=msg,
        temperature=0.3,
        max_tokens=1024,
        n=1
    )
    return response


def user_role_msg(content):
    return {"role": "user", "content": content}


def get_parser():
    parser = argparse.ArgumentParser(description='subtitle translator')
    parser.add_argument('-i', type=str, required=True, help='Input file path')
    parser.add_argument('-o', type=str, required=True, help='Output file path')
    parser.add_argument('-delay', default=1.5, type=float,
                        help='Sleep time between query')
    parser.add_argument('-start', default=1, type=int,
                        help='Start section (default: 1)')
    parser.add_argument('-max_section', type=int, default=4,
                        help='Max sections in one query')
    return parser


if __name__ == '__main__':

    parser = get_parser()
    args = parser.parse_args()

    system_msg = {"role": "system",
                  "content": "翻譯電影對話，將英文翻譯成繁體中文，只輸出翻譯內容並保持格式，我會直接提供內容"}

    message = [system_msg]

    subtitle_srt_file = args.i
    result_file = args.o
    max_section = args.max_section
    start = args.start
    delay = args.delay

    openai.api_key = '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'

    with open(subtitle_srt_file, 'r', encoding='utf-8') as f:
        all_subs = f.readlines()

    all_sections = ''.join(all_subs).split('\n\n')

    for section in all_sections[start-1:]:
        sub = '\n'.join(section.split('\n')[2:])
        message.append(user_role_msg(f"{sub}"))

        if len(message) > (max_section*2+1):
            message.pop(1)
            message.pop(1)

        response = get_response(message)
        response_content = response.choices[0].message
        message.append(response_content)

        with open(result_file, 'a', encoding='utf-8') as f:
            final_sub = '\n'.join(section.split(
                '\n')[:2] + response_content.content.split('\n'))
            print(final_sub)
            f.write(final_sub)
            f.write('\n\n')
        print('===')
        time.sleep(delay)
