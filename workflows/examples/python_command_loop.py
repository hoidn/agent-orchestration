from orchestrator.py import Command, cont, done, loop, when, workflow


work = Command("work", returns=int)


@workflow
def run(limit: int) -> int:
    return loop(
        state=0,
        max=limit,
        body=lambda count: when(
            count == 2,
            then=lambda: done(count),
            else_=lambda: cont(work(
                "python", "workflows/examples/python_command_loop_tool.py", count
            )),
        ),
        on_exhausted=lambda count: count,
    )
