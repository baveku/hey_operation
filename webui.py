import logging
import pdb
from email import message

from dotenv import load_dotenv

load_dotenv()
import argparse
import asyncio
import glob
import os

logger = logging.getLogger(__name__)

import gradio as gr
from gradio.themes import (Base, Citrus, Default, Glass, Monochrome, Ocean,
                           Origin, Soft)
from langchain_ollama import ChatOllama
from playwright.async_api import async_playwright

from browser_use.agent.service import Agent
from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.browser.context import (BrowserContextConfig,
                                         BrowserContextWindowSize)
from src.agent.custom_agent import CustomAgent
from src.agent.custom_prompts import (CustomAgentMessagePrompt,
                                      CustomSystemPrompt)
from src.browser.custom_browser import CustomBrowser
from src.browser.custom_context import (BrowserContextConfig,
                                        CustomBrowserContext)
from src.controller.custom_controller import CustomController
from src.utils import utils
from src.utils.agent_state import AgentState
from src.utils.default_config_settings import (default_config,
                                               load_config_from_file,
                                               save_config_to_file,
                                               save_current_config,
                                               update_ui_from_config)
from src.utils.utils import (capture_screenshot, get_latest_files,
                             update_model_dropdown)

# Global variables for persistence
_global_browser = None
_global_browser_context = None

# Create the global agent state instance
_global_agent_state = AgentState()

async def stop_agent():
    """Request the agent to stop and update UI with enhanced feedback"""
    global _global_agent_state, _global_browser_context, _global_browser

    try:
        # Request stop
        _global_agent_state.request_stop()

        # Update UI immediately
        message = "Stop requested - the agent will halt at the next safe point"
        logger.info(f"🛑 {message}")

        # Return UI updates
        return (
            message,                                        # errors_output
            gr.update(value="Stopping...", interactive=False),  # stop_button
            gr.update(interactive=False),                      # run_button
        )
    except Exception as e:
        error_msg = f"Error during stop: {str(e)}"
        logger.error(error_msg)
        return (
            error_msg,
            gr.update(value="Stop", interactive=True),
            gr.update(interactive=True)
        )
async def step_callback(browser_state, agent_output, step_num):
    """Callback function to be called after each step"""
    global _global_browser_context, _global_agent_state
    logger.info(f"Step {step_num}: {agent_output} - {browser_state}")
    


async def run_browser_agent(
        agent_type,
        llm_provider,
        llm_model_name,
        llm_temperature,
        llm_base_url,
        llm_api_key,
        use_own_browser,
        keep_browser_open,
        headless,
        disable_security,
        window_w,
        window_h,
        save_recording_path,
        save_agent_history_path,
        save_trace_path,
        enable_recording,
        task,
        add_infos,
        max_steps,
        use_vision,
        max_actions_per_step,
        tool_calling_method
):
    global _global_agent_state
    _global_agent_state.clear_stop()  # Clear any previous stop requests

    try:
        # Disable recording if the checkbox is unchecked
        if not enable_recording:
            save_recording_path = None

        # Ensure the recording directory exists if recording is enabled
        if save_recording_path:
            os.makedirs(save_recording_path, exist_ok=True)

        # Get the list of existing videos before the agent runs
        existing_videos = set()
        if save_recording_path:
            existing_videos = set(
                glob.glob(os.path.join(save_recording_path, "*.[mM][pP]4"))
                + glob.glob(os.path.join(save_recording_path, "*.[wW][eE][bB][mM]"))
            )

        # Run the agent
        llm = utils.get_llm_model(
            provider=llm_provider,
            model_name=llm_model_name,
            temperature=llm_temperature,
            base_url=llm_base_url,
            api_key=llm_api_key,
        )
        if agent_type == "org":
            final_result, errors, model_actions, model_thoughts, trace_file, history_file = await run_org_agent(
                llm=llm,
                use_own_browser=use_own_browser,
                keep_browser_open=keep_browser_open,
                headless=headless,
                disable_security=disable_security,
                window_w=window_w,
                window_h=window_h,
                save_recording_path=save_recording_path,
                save_agent_history_path=save_agent_history_path,
                save_trace_path=save_trace_path,
                task=task,
                max_steps=max_steps,
                use_vision=use_vision,
                max_actions_per_step=max_actions_per_step,
                tool_calling_method=tool_calling_method
            )
        elif agent_type == "custom":
            final_result, errors, model_actions, model_thoughts, trace_file, history_file = await run_custom_agent(
                llm=llm,
                use_own_browser=use_own_browser,
                keep_browser_open=keep_browser_open,
                headless=headless,
                disable_security=disable_security,
                window_w=window_w,
                window_h=window_h,
                save_recording_path=save_recording_path,
                save_agent_history_path=save_agent_history_path,
                save_trace_path=save_trace_path,
                task=task,
                add_infos=add_infos,
                max_steps=max_steps,
                use_vision=use_vision,
                max_actions_per_step=max_actions_per_step,
                tool_calling_method=tool_calling_method
            )
        else:
            raise ValueError(f"Invalid agent type: {agent_type}")

        # Get the list of videos after the agent runs (if recording is enabled)
        latest_video = None
        if save_recording_path:
            new_videos = set(
                glob.glob(os.path.join(save_recording_path, "*.[mM][pP]4"))
                + glob.glob(os.path.join(save_recording_path, "*.[wW][eE][bB][mM]"))
            )
            if new_videos - existing_videos:
                latest_video = list(new_videos - existing_videos)[0]  # Get the first new video

        return (
            final_result,
            errors,
            model_actions,
            model_thoughts,
            latest_video,
            trace_file,
            history_file,
            gr.update(value="Stop", interactive=True),  # Re-enable stop button
            gr.update(interactive=True)    # Re-enable run button
        )

    except gr.Error:
        raise

    except Exception as e:
        import traceback
        traceback.print_exc()
        errors = str(e) + "\n" + traceback.format_exc()
        return (
            '',                                         # final_result
            errors,                                     # errors
            '',                                         # model_actions
            '',                                         # model_thoughts
            None,                                       # latest_video
            None,                                       # history_file
            None,                                       # trace_file
            gr.update(value="Stop", interactive=True),  # Re-enable stop button
            gr.update(interactive=True)    # Re-enable run button
        )


async def run_org_agent(
        llm,
        use_own_browser,
        keep_browser_open,
        headless,
        disable_security,
        window_w,
        window_h,
        save_recording_path,
        save_agent_history_path,
        save_trace_path,
        task,
        max_steps,
        use_vision,
        max_actions_per_step,
        tool_calling_method
):
    try:
        global _global_browser, _global_browser_context, _global_agent_state
        
        # Clear any previous stop request
        _global_agent_state.clear_stop()

        extra_chromium_args = [f"--window-size={window_w},{window_h}"]
        if use_own_browser:
            chrome_path = os.getenv("CHROME_PATH", None)
            if chrome_path == "":
                chrome_path = None
            chrome_user_data = os.getenv("CHROME_USER_DATA", None)
            if chrome_user_data:
                extra_chromium_args += [f"--user-data-dir={chrome_user_data}"]
        else:
            chrome_path = None
            
        if _global_browser is None:
            _global_browser = Browser(
                config=BrowserConfig(
                    headless=headless,
                    disable_security=disable_security,
                    chrome_instance_path=chrome_path,
                    extra_chromium_args=extra_chromium_args,
                )
            )

        if _global_browser_context is None:
            _global_browser_context = await _global_browser.new_context(
                config=BrowserContextConfig(
                    trace_path=save_trace_path if save_trace_path else None,
                    save_recording_path=save_recording_path if save_recording_path else None,
                    no_viewport=False,
                    browser_window_size=BrowserContextWindowSize(
                        width=window_w, height=window_h
                    ),
                )
            )
            
        agent = Agent(
            task=task,
            llm=llm,
            use_vision=use_vision,
            browser=_global_browser,
            browser_context=_global_browser_context,
            max_actions_per_step=max_actions_per_step,
            tool_calling_method=tool_calling_method,
        )
        history = await agent.run(max_steps=max_steps)

        history_file = os.path.join(save_agent_history_path, f"{agent.agent_id}.json")
        agent.save_history(history_file)

        final_result = history.final_result()
        errors = history.errors()
        model_actions = history.model_actions()
        model_thoughts = history.model_thoughts()

        trace_file = get_latest_files(save_trace_path)

        return final_result, errors, model_actions, model_thoughts, trace_file.get('.zip'), history_file
    except Exception as e:
        import traceback
        traceback.print_exc()
        errors = str(e) + "\n" + traceback.format_exc()
        return '', errors, '', '', None, None
    finally:
        # Handle cleanup based on persistence configuration
        if not keep_browser_open:
            if _global_browser_context:
                await _global_browser_context.close()
                _global_browser_context = None

            if _global_browser:
                await _global_browser.close()
                _global_browser = None

async def run_custom_agent(
        llm,
        use_own_browser,
        keep_browser_open,
        headless,
        disable_security,
        window_w,
        window_h,
        save_recording_path,
        save_agent_history_path,
        save_trace_path,
        task,
        add_infos,
        max_steps,
        use_vision,
        max_actions_per_step,
        tool_calling_method
):
    try:
        global _global_browser, _global_browser_context, _global_agent_state

        # Clear any previous stop request
        _global_agent_state.clear_stop()

        extra_chromium_args = [f"--window-size={window_w},{window_h}"]
        if use_own_browser:
            chrome_path = os.getenv("CHROME_PATH", None)
            if chrome_path == "":
                chrome_path = None
            chrome_user_data = os.getenv("CHROME_USER_DATA", None)
            if chrome_user_data:
                extra_chromium_args += [f"--user-data-dir={chrome_user_data}"]
        else:
            chrome_path = None

        controller = CustomController()

        # Initialize global browser if needed
        if _global_browser is None:
            _global_browser = CustomBrowser(
                config=BrowserConfig(
                    headless=headless,
                    disable_security=disable_security,
                    chrome_instance_path=chrome_path,
                    extra_chromium_args=extra_chromium_args,
                )
            )

        if _global_browser_context is None:
            _global_browser_context = await _global_browser.new_context(
                config=BrowserContextConfig(
                    trace_path=save_trace_path if save_trace_path else None,
                    save_recording_path=save_recording_path if save_recording_path else None,
                    no_viewport=False,
                    browser_window_size=BrowserContextWindowSize(
                        width=window_w, height=window_h
                    ),
                )
            )
            
        # Create and run agent
        agent = CustomAgent(
            task=task,
            add_infos=add_infos,
            use_vision=use_vision,
            llm=llm,
            browser=_global_browser,
            browser_context=_global_browser_context,
            controller=controller,
            system_prompt_class=CustomSystemPrompt,
            agent_prompt_class=CustomAgentMessagePrompt,
            max_actions_per_step=max_actions_per_step,
            agent_state=_global_agent_state,
            tool_calling_method=tool_calling_method
        )
        history = await agent.run(max_steps=max_steps)

        history_file = os.path.join(save_agent_history_path, f"{agent.agent_id}.json")
        agent.save_history(history_file)

        final_result = history.final_result()
        errors = history.errors()
        model_actions = history.model_actions()
        model_thoughts = history.model_thoughts()

        trace_file = get_latest_files(save_trace_path)        

        return final_result, errors, model_actions, model_thoughts, trace_file.get('.zip'), history_file
    except Exception as e:
        import traceback
        traceback.print_exc()
        errors = str(e) + "\n" + traceback.format_exc()
        return '', errors, '', '', None, None
    finally:
        # Handle cleanup based on persistence configuration
        if not keep_browser_open:
            if _global_browser_context:
                await _global_browser_context.close()
                _global_browser_context = None

            if _global_browser:
                await _global_browser.close()
                _global_browser = None

async def run_with_stream(
    agent_type,
    llm_provider,
    llm_model_name,
    llm_temperature,
    llm_base_url,
    llm_api_key,
    use_own_browser,
    keep_browser_open,
    headless,
    disable_security,
    window_w,
    window_h,
    save_recording_path,
    save_agent_history_path,
    save_trace_path,
    enable_recording,
    task,
    add_infos,
    max_steps,
    use_vision,
    max_actions_per_step,
    tool_calling_method
):
    global _global_agent_state
    stream_vw = 80
    stream_vh = int(80 * window_h // window_w)
    if not headless:
        result = await run_browser_agent(
            agent_type=agent_type,
            llm_provider=llm_provider,
            llm_model_name=llm_model_name,
            llm_temperature=llm_temperature,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            use_own_browser=use_own_browser,
            keep_browser_open=keep_browser_open,
            headless=headless,
            disable_security=disable_security,
            window_w=window_w,
            window_h=window_h,
            save_recording_path=save_recording_path,
            save_agent_history_path=save_agent_history_path,
            save_trace_path=save_trace_path,
            enable_recording=enable_recording,
            task=task,
            add_infos=add_infos,
            max_steps=max_steps,
            use_vision=use_vision,
            max_actions_per_step=max_actions_per_step,
            tool_calling_method=tool_calling_method
        )
        # Add HTML content at the start of the result array
        html_content = f"<h1 style='width:{stream_vw}vw; height:{stream_vh}vh'>Using browser...</h1>"
        yield [html_content] + list(result)
    else:
        
        try:
            _global_agent_state.clear_stop()
            # Run the browser agent in the background
            agent_task = asyncio.create_task(
                run_browser_agent(
                    agent_type=agent_type,
                    llm_provider=llm_provider,
                    llm_model_name=llm_model_name,
                    llm_temperature=llm_temperature,
                    llm_base_url=llm_base_url,
                    llm_api_key=llm_api_key,
                    use_own_browser=use_own_browser,
                    keep_browser_open=keep_browser_open,
                    headless=headless,
                    disable_security=disable_security,
                    window_w=window_w,
                    window_h=window_h,
                    save_recording_path=save_recording_path,
                    save_agent_history_path=save_agent_history_path,
                    save_trace_path=save_trace_path,
                    enable_recording=enable_recording,
                    task=task,
                    add_infos=add_infos,
                    max_steps=max_steps,
                    use_vision=use_vision,
                    max_actions_per_step=max_actions_per_step,
                    tool_calling_method=tool_calling_method
                )
            )

            # Initialize values for streaming
            html_content = f"<h1 style='width:{stream_vw}vw; height:{stream_vh}vh'>Using browser...</h1>"
            final_result = errors = model_actions = model_thoughts = ""
            latest_videos = trace = history_file = None

            history: list = [{"role": "assistant", "content": "I'm thinking..."}]
            yield [
                html_content,
                final_result,
                errors,
                model_actions,
                model_thoughts,
                latest_videos,
                trace,
                history_file,
                gr.update(value="Stop", interactive=True),  # Re-enable stop button
                gr.update(interactive=True),  # Re-enable run button
                history
            ]
            now = _global_agent_state.now
            # Periodically update the stream while the agent task is running
            while not agent_task.done():
                try:
                    encoded_screenshot = await capture_screenshot(_global_browser_context)
                    
                    if encoded_screenshot is not None:
                        html_content = f'<img src="data:image/jpeg;base64,{encoded_screenshot}" style="width:{stream_vw}vw; height:{stream_vh}vh ; border:1px solid #ccc;">'
                    else:
                        html_content = f"<h1 style='width:{stream_vw}vw; height:{stream_vh}vh'>Waiting for browser session...</h1>"
                except Exception as e:
                    html_content = f"<h1 style='width:{stream_vw}vw; height:{stream_vh}vh'>Waiting for browser session...</h1>"

                if _global_agent_state and _global_agent_state.is_stop_requested():
                    history.append({"role": "assistant", "content": "Stop requested - the agent will halt at the next safe point"})
                    yield [
                        html_content,
                        final_result,
                        errors,
                        model_actions,
                        model_thoughts,
                        latest_videos,
                        trace,
                        history_file,
                        gr.update(value="Stopping...", interactive=False),  # stop_button
                        gr.update(interactive=False),  # run_button
                        history
                    ]
                    break
                else:
                    if _global_agent_state.will_update_model_thinking(now):
                        history.append({"role": "assistant", "content": _global_agent_state.get_model_thinking()})
                    yield [
                        html_content,
                        final_result,
                        errors,
                        model_actions,
                        model_thoughts,
                        latest_videos,
                        trace,
                        history_file,
                        gr.update(value="Stop", interactive=True),  # Re-enable stop button
                        gr.update(interactive=True),  # Re-enable run button
                        history
                    ]
                await asyncio.sleep(0.05)

            # Once the agent task completes, get the results
            try:
                result = await agent_task
                final_result, errors, model_actions, model_thoughts, latest_videos, trace, history_file, stop_button, run_button = result
                history.append({"role": "assistant", "content": final_result})
            except gr.Error:
                final_result = ""
                model_actions = ""
                model_thoughts = ""
                latest_videos = trace = history_file = None

            except Exception as e:
                errors = f"Agent error: {str(e)}"
                history.append({"role": "assistant", "content": errors})
            
            yield [
                html_content,
                final_result,
                errors,
                model_actions,
                model_thoughts,
                latest_videos,
                trace,
                history_file,
                stop_button,
                run_button,
                history
            ]

        except Exception as e:
            import traceback
            error_msg = {"role": "assistant", "content": f"Error: {str(e)}\n{traceback.format_exc()}"}
            yield [
                f"<h1 style='width:{stream_vw}vw; height:{stream_vh}vh'>Waiting for browser session...</h1>",
                "",
                f"Error: {str(e)}\n{traceback.format_exc()}",
                "",
                "",
                None,
                None,
                None,
                gr.update(value="Stop", interactive=True),  # Re-enable stop button
                gr.update(interactive=True),    # Re-enable run button
                [error_msg]
            ]

# Define the theme map globally
theme_map = {
    "Default": Default(),
    "Soft": Soft(),
    "Monochrome": Monochrome(),
    "Glass": Glass(),
    "Origin": Origin(),
    "Citrus": Citrus(),
    "Ocean": Ocean(),
    "Base": Base()
}

async def close_global_browser():
    global _global_browser, _global_browser_context

    if _global_browser_context:
        await _global_browser_context.close()
        _global_browser_context = None

    if _global_browser:
        await _global_browser.close()
        _global_browser = None
        
async def run_deep_search(research_task, max_search_iteration_input, max_query_per_iter_input, llm_provider, llm_model_name, llm_temperature, llm_base_url, llm_api_key, use_vision, headless):
    from src.utils.deep_research import deep_research
    
    llm = utils.get_llm_model(
            provider=llm_provider,
            model_name=llm_model_name,
            temperature=llm_temperature,
            base_url=llm_base_url,
            api_key=llm_api_key,
        )
    markdown_content, file_path = await deep_research(research_task, llm, 
                                                        max_search_iterations=max_search_iteration_input,
                                                        max_query_num=max_query_per_iter_input,
                                                        use_vision=use_vision,
                                                        headless=headless)
    return markdown_content, file_path
    

def create_ui(config, theme_name="Ocean"):
    css = """
    .gradio-container {
        max-width: 1800px !important;
        # margin: auto !important;
        padding-top: 20px !important;
    }
    .header-text {
        text-align: center;
        margin-bottom: 30px;
    }
    .theme-section {
        margin-bottom: 20px;
        padding: 15px;
        border-radius: 10px;
    }
    """

    with gr.Blocks(
            title="Autiom", theme=theme_map[theme_name], css=css
    ) as demo:
        local_inputs = gr.BrowserState(["", ""], storage_key="inputs", secret="ABCOK")
        with gr.Row():
            gr.Markdown(
                """
                # 🌐 AI Automation
                """,
                elem_classes=["header-text"],
            )

        with gr.Tabs() as tabs:
                with gr.TabItem("🤖 Run Agent", id=0):
                    with gr.Row():
                        with gr.Column(scale=1) as col:
                            with gr.Blocks(fill_height=True):
                                gr.Markdown(
                                    """
                                    ## 🤖 Agent Thinking
                                    """
                                )

                                chatbot = gr.Chatbot(
                                    value=[{"role": "assistant", "content": "I'm waiting..."}],
                                    type="messages",
                                    label="Agent",
                                )
                                
                            with gr.Column(scale=1):
                                task = gr.TextArea(
                                        label="Task Description",
                                        lines=5,
                                        max_lines=5,
                                        placeholder="Enter your task here...",
                                        info="Describe what you want the agent to do",
                                    )
                                add_infos = gr.TextArea(
                                    label="Additional Information",
                                    lines=3,
                                    max_lines=3,
                                    placeholder="Add any helpful context or instructions...",
                                    info="Optional hints to help the LLM complete the task",
                                )

                                @demo.load(inputs=[local_inputs], outputs=[task, add_infos])
                                def load_from_local_storage(saved_values):
                                    print("loading from local storage", saved_values)
                                    return saved_values[0], saved_values[1]
                                @gr.on([task.change, add_infos.change], inputs=[task, add_infos], outputs=[local_inputs])
                                def save_to_local_storage(username, password):
                                    return [username, password]
                                
                                with gr.Row():
                                    run_button = gr.Button("▶️ Run Agent", variant="primary", scale=2)
                                    stop_button = gr.Button("⏹️ Stop", variant="stop", scale=1)
                        with gr.Column(scale=2):
                            browser_view = gr.HTML(
                                value="<h1 style='width:100vh; height:68vh'>Waiting for browser session...</h1>",
                                label="Live Browser View",
                            )
                with gr.TabItem("📊 Results", id=6):
                    with gr.Group():
                        with gr.Row(equal_height=True):
                            with gr.Column():
                                with gr.Group():
                                    final_result_output = gr.Textbox(
                                        label="Final Result", lines=15, show_label=True
                                    )
                                with gr.Group():
                                    errors_output = gr.Textbox(
                                        label="Errors", lines=3, show_label=True
                                    )
                            recording_display = gr.Video(label="Latest Recording")
                        with gr.Row(equal_height=True):
                            with gr.Column():
                                model_actions_output = gr.Textbox(
                                    label="Model Actions", show_label=True
                                )
                                model_thoughts_output = gr.Textbox(
                                    label="Model Thoughts", show_label=True
                                )
                            with gr.Column():
                                trace_file = gr.File(label="Trace File")
                                agent_history_file = gr.File(label="Agent History")


                with gr.TabItem("⚙️ Settings", id=1):
                    with gr.Tabs() as settings_tabs:
                        with gr.TabItem("🕸️ Agent Setings", id=1):
                            with gr.Group():
                                agent_type = gr.Radio(
                                    ["org", "custom"],
                                    label="Agent Type",
                                    value=config['agent_type'],
                                    info="Select the type of agent to use",
                                )
                                with gr.Column():
                                    max_steps = gr.Slider(
                                        minimum=1,
                                        maximum=200,
                                        value=config['max_steps'],
                                        step=1,
                                        label="Max Run Steps",
                                        info="Maximum number of steps the agent will take",
                                    )
                                    max_actions_per_step = gr.Slider(
                                        minimum=1,
                                        maximum=20,
                                        value=config['max_actions_per_step'],
                                        step=1,
                                        label="Max Actions per Step",
                                        info="Maximum number of actions the agent will take per step",
                                    )
                                with gr.Column():
                                    use_vision = gr.Checkbox(
                                        label="Use Vision",
                                        value=config['use_vision'],
                                        info="Enable visual processing capabilities",
                                    )
                                    tool_calling_method = gr.Dropdown(
                                        label="Tool Calling Method",
                                        value=config['tool_calling_method'],
                                        interactive=True,
                                        allow_custom_value=True,  # Allow users to input custom model names
                                        choices=["auto", "json_schema", "function_calling"],
                                        info="Tool Calls Funtion Name",
                                        visible=False
                                    )

                        with gr.TabItem("🔧 LLM Configuration", id=2):
                            with gr.Group():
                                llm_provider = gr.Dropdown(
                                    choices=[provider for provider,model in utils.model_names.items()],
                                    label="LLM Provider",
                                    value=config['llm_provider'],
                                    info="Select your preferred language model provider"
                                )
                                llm_model_name = gr.Dropdown(
                                    label="Model Name",
                                    choices=utils.model_names['openai'],
                                    value=config['llm_model_name'],
                                    interactive=True,
                                    allow_custom_value=True,  # Allow users to input custom model names
                                    info="Select a model from the dropdown or type a custom model name"
                                )
                                llm_temperature = gr.Slider(
                                    minimum=0.0,
                                    maximum=2.0,
                                    value=config['llm_temperature'],
                                    step=0.1,
                                    label="Temperature",
                                    info="Controls randomness in model outputs"
                                )
                                with gr.Row():
                                    llm_base_url = gr.Textbox(
                                        label="Base URL",
                                        value=config['llm_base_url'],
                                        info="API endpoint URL (if required)"
                                    )
                                    llm_api_key = gr.Textbox(
                                        label="API Key",
                                        type="password",
                                        value=config['llm_api_key'],
                                        info="Your API key (leave blank to use .env)"
                                    )

                        with gr.TabItem("🌐 Browser Settings", id=3):
                            with gr.Group():
                                with gr.Row():
                                    use_own_browser = gr.Checkbox(
                                        label="Use Own Browser",
                                        value=config['use_own_browser'],
                                        info="Use your existing browser instance",
                                    )
                                    keep_browser_open = gr.Checkbox(
                                        label="Keep Browser Open",
                                        value=config['keep_browser_open'],
                                        info="Keep Browser Open between Tasks",
                                    )
                                    headless = gr.Checkbox(
                                        label="Headless Mode",
                                        value=config['headless'],
                                        info="Run browser without GUI",
                                    )
                                    disable_security = gr.Checkbox(
                                        label="Disable Security",
                                        value=config['disable_security'],
                                        info="Disable browser security features",
                                    )
                                    enable_recording = gr.Checkbox(
                                        label="Enable Recording",
                                        value=config['enable_recording'],
                                        info="Enable saving browser recordings",
                                    )

                                with gr.Row():
                                    window_w = gr.Number(
                                        label="Window Width",
                                        value=config['window_w'],
                                        info="Browser window width",
                                    )
                                    window_h = gr.Number(
                                        label="Window Height",
                                        value=config['window_h'],
                                        info="Browser window height",
                                    )

                                save_recording_path = gr.Textbox(
                                    label="Recording Path",
                                    placeholder="e.g. ./tmp/record_videos",
                                    value=config['save_recording_path'],
                                    info="Path to save browser recordings",
                                    interactive=True,  # Allow editing only if recording is enabled
                                )

                                save_trace_path = gr.Textbox(
                                    label="Trace Path",
                                    placeholder="e.g. ./tmp/traces",
                                    value=config['save_trace_path'],
                                    info="Path to save Agent traces",
                                    interactive=True,
                                )

                                save_agent_history_path = gr.Textbox(
                                    label="Agent History Save Path",
                                    placeholder="e.g., ./tmp/agent_history",
                                    value=config['save_agent_history_path'],
                                    info="Specify the directory where agent history should be saved.",
                                    interactive=True,
                                )

                        

                        with gr.TabItem("📁 Configuration", id=5):
                            with gr.Group():
                                config_file_input = gr.File(
                                    label="Load Config File",
                                    file_types=[".pkl"],
                                    interactive=True
                                )

                                load_config_button = gr.Button("Load Existing Config From File", variant="primary")
                                save_config_button = gr.Button("Save Current Config", variant="primary")

                                config_status = gr.Textbox(
                                    label="Status",
                                    lines=2,
                                    interactive=False
                                )

                            load_config_button.click(
                                fn=update_ui_from_config,
                                inputs=[config_file_input],
                                outputs=[
                                    agent_type, max_steps, max_actions_per_step, use_vision, tool_calling_method,
                                    llm_provider, llm_model_name, llm_temperature, llm_base_url, llm_api_key,
                                    use_own_browser, keep_browser_open, headless, disable_security, enable_recording,
                                    window_w, window_h, save_recording_path, save_trace_path, save_agent_history_path,
                                    task, config_status
                                ]
                            )

                            save_config_button.click(
                                fn=save_current_config,
                                inputs=[
                                    agent_type, max_steps, max_actions_per_step, use_vision, tool_calling_method,
                                    llm_provider, llm_model_name, llm_temperature, llm_base_url, llm_api_key,
                                    use_own_browser, keep_browser_open, headless, disable_security,
                                    enable_recording, window_w, window_h, save_recording_path, save_trace_path,
                                    save_agent_history_path, task,
                                ],  
                                outputs=[config_status]
                            )

                            # Bind the stop button click event after errors_output is defined
                            stop_button.click(
                                fn=stop_agent,
                                inputs=[],
                                outputs=[errors_output, stop_button, run_button],
                            )

                            # Run button click handler
                            run_button.click(
                                fn=run_with_stream,
                                    inputs=[
                                        agent_type, llm_provider, llm_model_name, llm_temperature, llm_base_url, llm_api_key,
                                        use_own_browser, keep_browser_open, headless, disable_security, window_w, window_h,
                                        save_recording_path, save_agent_history_path, save_trace_path,  # Include the new path
                                        enable_recording, task, add_infos, max_steps, use_vision, max_actions_per_step, tool_calling_method,
                                    ],
                                outputs=[
                                    browser_view,           # Browser view
                                    final_result_output,    # Final result
                                    errors_output,          # Errors
                                    model_actions_output,   # Model actions
                                    model_thoughts_output,  # Model thoughts
                                    recording_display,      # Latest recording
                                    trace_file,             # Trace file
                                    agent_history_file,     # Agent history file
                                    stop_button,            # Stop button
                                    run_button,             # Run button
                                    chatbot                 # Chatbot        
                                ],
                            )

                        with gr.TabItem("🎥 Recordings", id=7):
                            def list_recordings(save_recording_path):
                                if not os.path.exists(save_recording_path):
                                    return []

                                # Get all video files
                                recordings = glob.glob(os.path.join(save_recording_path, "*.[mM][pP]4")) + glob.glob(os.path.join(save_recording_path, "*.[wW][eE][bB][mM]"))

                                # Sort recordings by creation time (oldest first)
                                recordings.sort(key=os.path.getctime)

                                # Add numbering to the recordings
                                numbered_recordings = []
                                for idx, recording in enumerate(recordings, start=1):
                                    filename = os.path.basename(recording)
                                    numbered_recordings.append((recording, f"{idx}. {filename}"))

                                return numbered_recordings

                            recordings_gallery = gr.Gallery(
                                label="Recordings",
                                value=list_recordings(config['save_recording_path']),
                                columns=3,
                                height="auto",
                                object_fit="contain"
                            )

                            refresh_button = gr.Button("🔄 Refresh Recordings", variant="secondary")
                            refresh_button.click(
                                fn=list_recordings,
                                inputs=save_recording_path,
                                outputs=recordings_gallery
                            )

        # Attach the callback to the LLM provider dropdown
        llm_provider.change(
            lambda provider, api_key, base_url: update_model_dropdown(provider, api_key, base_url),
            inputs=[llm_provider, llm_api_key, llm_base_url],
            outputs=llm_model_name
        )

        # Add this after defining the components
        enable_recording.change(
            lambda enabled: gr.update(interactive=enabled),
            inputs=enable_recording,
            outputs=save_recording_path
        )

        use_own_browser.change(fn=close_global_browser)
        keep_browser_open.change(fn=close_global_browser)

    return demo


parser = argparse.ArgumentParser(description="Gradio UI for Browser Agent")
parser.add_argument("--ip", type=str, default="127.0.0.1", help="IP address to bind to")
parser.add_argument("--port", type=int, default=7788, help="Port to listen on")
parser.add_argument("--theme", type=str, default="Ocean", choices=theme_map.keys(), help="Theme to use for the UI")
parser.add_argument("--dark-mode", action="store_true", help="Enable dark mode")
args = parser.parse_args()

config_dict = default_config()
demo = create_ui(config_dict, theme_name=args.theme)

if __name__ == '__main__':
    demo.launch(server_name=args.ip, server_port=args.port)